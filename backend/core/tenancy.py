"""
Application-layer tenant isolation.

This is the FIRST of two independent layers. The second is Postgres row-level
security (see migrations 0002_rls_policies). Either layer alone would catch
most bugs; together they catch every cross-tenant access we can think of.

Rules:
  * Every tenant-scoped model declares `objects = TenantManager()`.
  * Queries MUST call `.for_org(org)` before accessing rows.
  * Calling `.all()`, `.filter()`, etc. WITHOUT a prior `.for_org()` raises
    `TenantContextMissing` — loud failure beats silent leakage.
  * Bulk operations (`bulk_create`, etc.) require the caller to pass `org` in
    the model instance itself; we don't try to autoset it.
"""

from __future__ import annotations

from typing import Any

from django.db import models


class TenantContextMissing(RuntimeError):
    """Raised when a tenant-scoped query is made without `.for_org(...)`."""


class TenantQuerySet(models.QuerySet):
    _org_scoped: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._org_scoped = False

    def _clone(self, **kwargs: Any) -> "TenantQuerySet":
        clone = super()._clone(**kwargs)
        clone._org_scoped = self._org_scoped
        return clone

    def for_org(self, org) -> "TenantQuerySet":
        if org is None:
            raise TenantContextMissing("for_org(None) is not allowed")
        org_id = getattr(org, "id", org)
        qs = self.filter(organization_id=org_id)
        qs._org_scoped = True
        return qs

    def _check_scoped(self, op: str) -> None:
        if not self._org_scoped:
            raise TenantContextMissing(
                f"Refusing to {op} on a tenant-scoped model without calling "
                f".for_org(org) first. Call qs.for_org(request_org) before "
                f"materializing."
            )

    # Materializers — gate them all.
    def _fetch_all(self) -> None:
        self._check_scoped("iterate")
        super()._fetch_all()

    def count(self) -> int:
        self._check_scoped("count")
        return super().count()

    def exists(self) -> bool:
        self._check_scoped("exists()")
        return super().exists()

    def get(self, *args: Any, **kwargs: Any):
        self._check_scoped("get()")
        return super().get(*args, **kwargs)

    def first(self):
        self._check_scoped("first()")
        return super().first()

    def last(self):
        self._check_scoped("last()")
        return super().last()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Bound to TenantQuerySet — exposes `.for_org(org)` as the entry point."""

    use_in_migrations = True


class TenantModel(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.PROTECT,
        related_name="+",
        db_index=True,
    )
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"   # <-- was "objects"