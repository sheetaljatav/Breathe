"""
Tenant isolation — application layer.

These tests verify the FIRST of two layers (the ORM-side TenantQuerySet).
RLS at the DB level is verified separately in test_rls.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.tenancy import TenantContextMissing
from emissions.models import ActivityRecord


pytestmark = pytest.mark.django_db


def _make_activity(org, category, unit, value: str) -> ActivityRecord:
    return ActivityRecord.objects.create(
        organization=org,
        category=category,
        unit=unit,
        activity_date=date(2025, 4, 1),
        value=Decimal(value),
    )


def test_unscoped_query_raises(org_acme, cat_electricity, kwh):
    _make_activity(org_acme, cat_electricity, kwh, "100")
    with pytest.raises(TenantContextMissing):
        list(ActivityRecord.objects.all())
    with pytest.raises(TenantContextMissing):
        ActivityRecord.objects.count()
    with pytest.raises(TenantContextMissing):
        ActivityRecord.objects.first()


def test_for_org_scopes_correctly(org_acme, org_globex, cat_electricity, kwh):
    _make_activity(org_acme, cat_electricity, kwh, "100")
    _make_activity(org_acme, cat_electricity, kwh, "200")
    _make_activity(org_globex, cat_electricity, kwh, "999")

    assert ActivityRecord.objects.for_org(org_acme).count() == 2
    assert ActivityRecord.objects.for_org(org_globex).count() == 1


def test_for_org_with_none_raises(org_acme):
    with pytest.raises(TenantContextMissing):
        ActivityRecord.objects.for_org(None)


def test_chained_filter_remains_scoped(org_acme, org_globex, cat_electricity, kwh):
    _make_activity(org_acme, cat_electricity, kwh, "100")
    _make_activity(org_globex, cat_electricity, kwh, "100")

    # Chaining keeps scoping; filtering for a value that exists in both orgs
    # only returns the Acme row.
    qs = ActivityRecord.objects.for_org(org_acme).filter(value=Decimal("100"))
    assert qs.count() == 1
    assert qs.first().organization_id == org_acme.id
