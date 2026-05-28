"""
Tenant isolation — Postgres row-level security (the second layer).

These tests bypass the ORM and use raw SQL to prove RLS holds even when an
engineer writes a query that forgets `.for_org()`. They require a non-
superuser role (superusers bypass RLS). In dev, we create a session-scoped
role via SET ROLE on a no-login privilege group — pragmatic for testing.

Skipped automatically if the DB is not Postgres (e.g. someone runs the
suite against SQLite).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection, transaction

from emissions.models import ActivityRecord


pytestmark = pytest.mark.django_db(transaction=True)


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


@pytest.fixture
def rls_role():
    """
    Create a NOLOGIN role for the duration of this test, then SET ROLE to it.
    Postgres applies RLS to non-superusers; this gives us a non-superuser
    context without changing the connection.
    """
    if not _is_postgres():
        pytest.skip("RLS tests require Postgres.")
    with connection.cursor() as cur:
        cur.execute("CREATE ROLE breathe_rls_test NOLOGIN")
        cur.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO breathe_rls_test")
        cur.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO breathe_rls_test")
        cur.execute("SET ROLE breathe_rls_test")
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("DROP ROLE IF EXISTS breathe_rls_test")


def _seed_two_orgs(org_acme, org_globex, cat_electricity, kwh):
    ActivityRecord.objects.create(
        organization=org_acme, category=cat_electricity, unit=kwh,
        activity_date=date(2025, 4, 1), value=Decimal("100"),
    )
    ActivityRecord.objects.create(
        organization=org_globex, category=cat_electricity, unit=kwh,
        activity_date=date(2025, 4, 1), value=Decimal("999"),
    )


def test_rls_filters_to_current_org(org_acme, org_globex, cat_electricity, kwh, rls_role):
    _seed_two_orgs(org_acme, org_globex, cat_electricity, kwh)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config(%s, %s, false)",
            [settings.RLS_ORG_GUC, str(org_acme.id)],
        )
        cur.execute("SELECT COUNT(*) FROM activity_record")
        (n,) = cur.fetchone()
        assert n == 1


def test_rls_blocks_cross_org_select(org_acme, org_globex, cat_electricity, kwh, rls_role):
    _seed_two_orgs(org_acme, org_globex, cat_electricity, kwh)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config(%s, %s, false)",
            [settings.RLS_ORG_GUC, str(org_globex.id)],
        )
        cur.execute("SELECT value FROM activity_record")
        rows = cur.fetchall()
        assert all(row[0] == Decimal("999") for row in rows)


def test_rls_with_no_org_returns_zero_rows(org_acme, org_globex, cat_electricity, kwh, rls_role):
    _seed_two_orgs(org_acme, org_globex, cat_electricity, kwh)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config(%s, '', false)", [settings.RLS_ORG_GUC]
        )
        cur.execute("SELECT COUNT(*) FROM activity_record")
        (n,) = cur.fetchone()
        # Empty-string GUC → policy compares `organization_id::text = ''` which
        # is FALSE for every real row → no rows visible. (Same outcome as the
        # GUC being unset, where current_setting returns NULL and the
        # comparison evaluates to NULL.)
        assert n == 0
