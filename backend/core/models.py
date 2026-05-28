"""
Core models.

Three tables here, each with a specific job:

  Organization  — the tenant root (shared-DB, shared-schema multi-tenancy).
  Membership    — User × Organization with a role. Composite unique.
  AuditLog      — append-only event log. Insert-only at the DB level: the
                  migration 0003_audit_immutability installs BEFORE UPDATE /
                  DELETE triggers that RAISE EXCEPTION for any role, so even
                  buggy app code (or raw SQL) cannot rewrite history.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Organization(models.Model):
    """Tenant root. One client company = one Organization."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class MembershipRole(models.TextChoices):
    ANALYST = "analyst", "Analyst"
    ADMIN = "admin", "Admin"


class Membership(models.Model):
    """User's role within an Organization. A user can belong to multiple orgs."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=MembershipRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "membership"
        unique_together = [("organization", "user")]
        indexes = [models.Index(fields=["user", "organization"])]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"


class AuditAction(models.TextChoices):
    CREATED = "CREATED", "Created"
    UPDATED = "UPDATED", "Updated"
    APPROVED = "APPROVED", "Approved"
    FLAGGED = "FLAGGED", "Flagged"
    REJECTED = "REJECTED", "Rejected"
    LOCKED = "LOCKED", "Locked"
    UNLOCKED = "UNLOCKED", "Unlocked"
    REPARSED = "REPARSED", "Re-parsed"
    LOGGED_IN = "LOGGED_IN", "Logged in"


class AuditLog(models.Model):
    """
    Append-only event log.

    Why fields are shaped this way:
      * `id` is bigserial (monotonic) — ordering by id is ordering by time
        even if clocks skew.
      * `request_id` matches the X-Request-ID we put in structlog and on
        the HTTP response — one ID stitches together a Sentry error, an
        HTTP access log line, and the rows changed by that request.
      * `before` / `after` are JSONB snapshots so we can answer "what did
        this row look like before that edit" without joining anywhere.
      * `target_type` + `target_id` is a generic FK — one audit table for
        every model rather than one per model. We pay no FK integrity for
        this and that's deliberate: when a row gets hard-deleted (it
        shouldn't, but...), the audit history of it survives.

    The migration 0003_audit_immutability installs BEFORE UPDATE / DELETE
    triggers on this table that always RAISE EXCEPTION. INSERT is the only
    permitted DML. (We chose triggers over REVOKE because triggers apply to
    every role including superuser, which makes the protection testable in
    dev — see DECISIONS.md.)
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="+", db_index=True
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    request_id = models.CharField(max_length=64, db_index=True)
    action = models.CharField(max_length=24, choices=AuditAction.choices)
    target_type = models.CharField(max_length=64)        # e.g. "emissions.ActivityRecord"
    target_id = models.BigIntegerField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(
                fields=["organization", "target_type", "target_id", "-created_at"],
                name="auditlog_target_idx",
            ),
        ]
        ordering = ("-id",)

    def save(self, *args, **kwargs) -> None:
        # Enforce at the model layer too — defense in depth alongside the
        # DB-level triggers in migration 0003_audit_immutability.
        if self.pk is not None:
            raise PermissionError("audit_log rows are immutable; INSERT-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("audit_log rows are immutable; DELETE is forbidden.")
