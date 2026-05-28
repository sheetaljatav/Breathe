"""
Helpers for resolving the current request's org and asserting membership.

Every tenant-scoped DRF view should call `current_org(request)` at the top
to pin the org, then pass it to `.for_org(org)` for any queryset.
"""

from __future__ import annotations

from django.http import HttpRequest
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import Membership, Organization


def current_org(request: HttpRequest) -> Organization | None:
    """
    Resolve the org pinned to this request.

    Order:
      1. X-Org-ID header set by the org switcher in the UI — validated against
         the user's memberships.
      2. The user's first membership (stable order by id).

    Returns None for anonymous requests.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    requested = request.META.get("HTTP_X_ORG_ID")
    if requested and requested.isdigit():
        org_id = int(requested)
        if not Membership.objects.filter(user=user, organization_id=org_id).exists():
            raise PermissionDenied("Not a member of the requested organization.")
        return Organization.objects.filter(pk=org_id).first()

    m = (
        Membership.objects.filter(user=user)
        .select_related("organization")
        .order_by("id")
        .first()
    )
    return m.organization if m else None


def require_org(request: HttpRequest) -> Organization:
    """Like current_org but raises 404 if there's no org context."""
    org = current_org(request)
    if org is None:
        raise NotFound("No organization context.")
    return org


def require_role(request: HttpRequest, org: Organization, *allowed: str) -> Membership:
    """Assert the requesting user has one of the listed roles in `org`."""
    m = Membership.objects.filter(user=request.user, organization=org).first()
    if m is None or m.role not in allowed:
        raise PermissionDenied(f"Role required: one of {allowed}.")
    return m
