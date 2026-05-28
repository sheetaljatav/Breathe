"""
Audit log immutability — DB-level triggers.

The model save()/delete() guards are the first layer; these tests prove the
triggers from migration 0003_audit_immutability hold even if someone bypasses
the model layer by writing raw SQL.

Skipped against SQLite.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.utils import InternalError, ProgrammingError

from core.audit import record_change
from core.models import AuditAction, AuditLog


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def an_audit_row(org_acme, user_acme):
    return record_change(
        organization=org_acme,
        actor=user_acme,
        action=AuditAction.CREATED,
        target=org_acme,           # any model with a pk works
        before=None,
        after={"name": "Acme Corp"},
    )


def test_model_layer_save_blocks_update(an_audit_row):
    """The save() override on AuditLog refuses pk!=None inserts."""
    with pytest.raises(PermissionError):
        an_audit_row.save()


def test_model_layer_delete_blocks(an_audit_row):
    with pytest.raises(PermissionError):
        an_audit_row.delete()


def test_db_trigger_blocks_raw_update(an_audit_row):
    if connection.vendor != "postgresql":
        pytest.skip("Trigger lives in Postgres.")
    with pytest.raises((InternalError, ProgrammingError)):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE audit_log SET reason = 'tampered' WHERE id = %s", [an_audit_row.id])


def test_db_trigger_blocks_raw_delete(an_audit_row):
    if connection.vendor != "postgresql":
        pytest.skip("Trigger lives in Postgres.")
    with pytest.raises((InternalError, ProgrammingError)):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("DELETE FROM audit_log WHERE id = %s", [an_audit_row.id])


def test_insert_still_works(org_acme, user_acme):
    # Sanity: triggers don't affect INSERT.
    before_count = AuditLog.objects.count()
    record_change(
        organization=org_acme, actor=user_acme,
        action=AuditAction.UPDATED, target=org_acme,
        after={"x": 1},
    )
    assert AuditLog.objects.count() == before_count + 1
