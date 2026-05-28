"""
The `record_change()` helper.

One function to write an AuditLog row. Called from:
  * model save() overrides on tenant-scoped models that want change tracking
  * review actions (approve/flag/reject/lock/unlock) explicitly
  * the auth views (LOGGED_IN)

It pulls the actor and request_id from the *current request*, which it gets
via the structlog contextvars bound by RequestIdMiddleware. This avoids
threading request through every model save and keeps the surface tiny.
"""

from __future__ import annotations

from typing import Any

import structlog

from .models import AuditAction, AuditLog


def record_change(
    *,
    organization,
    action: AuditAction | str,
    target,
    actor=None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    """
    Append an audit row.

    `target` is a model instance; we derive target_type from its app_label and
    class name, and target_id from its pk.

    `actor` defaults to whatever is currently bound in structlog contextvars
    (set by the view layer from request.user). Passing it explicitly is the
    safer call from inside Celery tasks where there's no request.
    """
    ctx = structlog.contextvars.get_contextvars()
    request_id = ctx.get("request_id", "")
    if actor is None:
        actor = ctx.get("actor_user")  # may be None for system actions

    target_type = f"{target._meta.app_label}.{target.__class__.__name__}"

    row = AuditLog(
        organization=organization,
        actor_user=actor,
        request_id=request_id,
        action=action.value if hasattr(action, "value") else action,
        target_type=target_type,
        target_id=target.pk,
        before=before,
        after=after,
        reason=reason,
    )
    row.save(force_insert=True)
    return row
