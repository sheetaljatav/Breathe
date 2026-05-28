"""
Pytest fixtures.

Most tests run inside Django's transactional test DB (rollback after each test).
For RLS tests specifically, we need to be careful: RLS policies use a session
GUC (`app.current_org_id`) that we set per-test, then clear in teardown.

`celery_eager` autouse fixture makes every Celery task run synchronously in the
caller's process so we don't need a worker (or a broker) up to run tests.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

from core.models import Membership, MembershipRole, Organization
from emissions.models import (
    CanonicalUnit,
    EmissionCategory,
    EmissionFactor,
    Scope,
    UnitDimension,
)


@pytest.fixture
def kwh(db):
    return CanonicalUnit.objects.create(code="kWh", label="Kilowatt-hour", dimension=UnitDimension.ENERGY)


@pytest.fixture
def liters(db):
    return CanonicalUnit.objects.create(code="L", label="Liter", dimension=UnitDimension.VOLUME)


@pytest.fixture
def cat_electricity(db, kwh):
    return EmissionCategory.objects.create(
        code="purchased_electricity",
        label="Purchased electricity",
        scope=Scope.SCOPE_2,
        default_unit=kwh,
        ghg_protocol_ref="GHG Protocol Scope 2",
    )


@pytest.fixture
def factor_electricity(db, cat_electricity, kwh):
    return EmissionFactor.objects.create(
        category=cat_electricity, region="global", year=2025, unit=kwh,
        kg_co2e_per_unit=Decimal("0.475"),
        source="IEA 2024 global average",
        effective_from=date(2025, 1, 1),
    )


@pytest.fixture
def org_acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme")


@pytest.fixture
def org_globex(db):
    return Organization.objects.create(name="Globex", slug="globex")


@pytest.fixture
def user_acme(db, django_user_model, org_acme):
    u = django_user_model.objects.create_user(
        username="analyst@acme.test", email="analyst@acme.test", password="x")
    Membership.objects.create(organization=org_acme, user=u, role=MembershipRole.ANALYST)
    return u


@pytest.fixture
def user_globex(db, django_user_model, org_globex):
    u = django_user_model.objects.create_user(
        username="analyst@globex.test", email="analyst@globex.test", password="x")
    Membership.objects.create(organization=org_globex, user=u, role=MembershipRole.ANALYST)
    return u
