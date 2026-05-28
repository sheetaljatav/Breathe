"""
Optimistic concurrency on ActivityRecord PATCH.

Verifies the If-Match contract: two analysts editing the same row →
second save returns 412 Precondition Failed with the current state in body.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from emissions.models import ActivityRecord


pytestmark = pytest.mark.django_db


@pytest.fixture
def record(org_acme, cat_electricity, kwh, user_acme):
    return ActivityRecord.objects.create(
        organization=org_acme, category=cat_electricity, unit=kwh,
        activity_date=date(2025, 4, 1), value=Decimal("100"),
    )


def _client(user, org):
    c = APIClient()
    c.force_authenticate(user)
    c.defaults["HTTP_X_ORG_ID"] = str(org.id)
    return c


def test_patch_with_correct_if_match_succeeds(record, user_acme, org_acme):
    c = _client(user_acme, org_acme)
    r = c.patch(
        f"/api/activities/{record.id}/",
        data={"value": "150"},
        format="json",
        HTTP_IF_MATCH=str(record.version),
    )
    assert r.status_code == 200, r.content
    assert r.json()["version"] == record.version + 1


def test_patch_with_stale_if_match_returns_412(record, user_acme, org_acme):
    c = _client(user_acme, org_acme)
    # First edit advances version to 2.
    c.patch(
        f"/api/activities/{record.id}/",
        data={"value": "150"},
        format="json",
        HTTP_IF_MATCH=str(record.version),
    )
    # Second edit using the original version 1 should now fail.
    r = c.patch(
        f"/api/activities/{record.id}/",
        data={"value": "200"},
        format="json",
        HTTP_IF_MATCH=str(record.version),
    )
    assert r.status_code == 412
    body = r.json()
    assert body["current_version"] == record.version + 1
    assert "current" in body
