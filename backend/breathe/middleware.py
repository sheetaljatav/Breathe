"""
Two cross-cutting middlewares:

1. RequestIdMiddleware — generates or accepts an inbound `X-Request-ID`, binds
   it to structlog's contextvars (so every log line in this request carries it),
   echoes it back on the response, and exposes it as `request.request_id` for
   the audit-log writer.

2. TenantRLSMiddleware — sets the Postgres GUC `app.current_org_id` for the
   current connection so RLS policies can enforce tenant isolation at the DB
   layer. This is the second of two independent tenant-isolation layers (the
   first being TenantQuerySet at the ORM layer).
"""

from __future__ import annotations

import uuid
from typing import Callable

import structlog
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse


_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
_REQUEST_ID_RESPONSE = "X-Request-ID"


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rid = request.META.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.request_id = rid                                    # type: ignore[attr-defined]
        structlog.contextvars.clear_contextvars()
        bound = {
            "request_id": rid,
            "method": request.method,
            "path": request.path,
        }
        # `actor_user` is read by core.audit.record_change() as a fallback when
        # a caller doesn't pass actor=... explicitly. Bind it here so the fallback
        # is actually populated rather than always returning None.
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            bound["actor_user"] = user
        structlog.contextvars.bind_contextvars(**bound)
        try:
            response = self.get_response(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response[_REQUEST_ID_RESPONSE] = rid
        return response


class TenantRLSMiddleware:
    """
    Set Postgres session variables that RLS policies read.

    We use SET LOCAL inside an implicit transaction. Django opens a transaction
    per request when ATOMIC_REQUESTS is set; we don't rely on that. Instead, we
    use `SELECT set_config(name, value, true)` (the third arg `true` scopes it
    to the current transaction), which is safe to call outside an explicit
    transaction — it becomes a session-scoped set in that case, which we then
    clear in the response phase.

    Anonymous requests get an empty string, which RLS policies treat as "no
    org" — every tenant-scoped query returns zero rows. This is the correct
    failure mode.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        org_id = self._resolve_org_id(request)
        user_id = getattr(getattr(request, "user", None), "id", None) or ""

        with connection.cursor() as cur:
            cur.execute(
                "SELECT set_config(%s, %s, false), set_config(%s, %s, false)",
                [settings.RLS_ORG_GUC, str(org_id or ""),
                 settings.RLS_USER_GUC, str(user_id or "")],
            )
        try:
            return self.get_response(request)
        finally:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT set_config(%s, '', false), set_config(%s, '', false)",
                    [settings.RLS_ORG_GUC, settings.RLS_USER_GUC],
                )

    @staticmethod
    def _resolve_org_id(request: HttpRequest) -> int | None:
        """
        Resolve current org from (a) explicit X-Org-ID header (org switcher)
        or (b) the user's first membership. Header always wins, but the view
        layer must validate that the user is a member of the requested org.
        """
        header_org = request.META.get("HTTP_X_ORG_ID")
        if header_org and header_org.isdigit():
            return int(header_org)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        # Lazy import to avoid circular import at module load.
        from core.models import Membership
        m = Membership.objects.filter(user=user).order_by("id").first()
        return m.organization_id if m else None
