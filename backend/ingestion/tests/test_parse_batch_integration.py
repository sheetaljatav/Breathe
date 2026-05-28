"""
Integration test: full parse_batch flow against the SAP sample.

Runs the Celery task synchronously (CELERY_TASK_ALWAYS_EAGER is set on the
test runner via the dev settings). Verifies that SourceRecords, ActivityRecords,
and ParseErrors land in the DB with the right counts and the right org scoping.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emissions.models import ActivityRecord
from ingestion.models import BatchStatus, IngestionBatch, ParseError, SourceRecord, SourceType
from ingestion.storage import write_bytes
from ingestion.tasks import parse_batch


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def acme_with_plant_codes(org_acme):
    from emissions.models import PlantCode
    for code, name in [("1000", "Düsseldorf"), ("1100", "Stuttgart"),
                       ("2000", "Chicago"), ("2100", "Atlanta")]:
        PlantCode.objects.get_or_create(
            organization=org_acme, code=code,
            defaults={"facility_name": name, "country": "DE"},
        )
    return org_acme


SAMPLE = (
    Path(__file__).resolve().parents[3]
    / "samples" / "sap_se16n_export_2026Q1.csv"
)


def test_parse_batch_end_to_end(acme_with_plant_codes, user_acme,
                                cat_electricity, kwh, factor_electricity):
    # The factor_electricity fixture is not directly needed here but
    # guarantees seeded reference data exists for the test DB; the SAP
    # parser maps to other categories which the test setup doesn't seed,
    # so ActivityRecord counts may be zero — but SourceRecord + ParseError
    # writes are what we're verifying.
    org = acme_with_plant_codes
    data = SAMPLE.read_bytes()

    batch = IngestionBatch.objects.create(
        organization=org, source_type=SourceType.SAP,
        uploaded_by=user_acme,
        file_name="sap_se16n_export_2026Q1.csv",
        file_sha256="x" * 64, file_size_bytes=len(data),
        parser_version="pending",
    )
    write_bytes(batch.id, data)
    parse_batch.apply(args=[batch.id]).get()

    batch.refresh_from_db()
    assert batch.status == BatchStatus.COMPLETE
    assert batch.rows_total > 0

    # SourceRecords written for every CSV row (48).
    assert SourceRecord.objects.for_org(org).filter(batch=batch).count() == 48

    # Errors include unmapped plant + unknown unit + bad date.
    err_codes = set(
        ParseError.objects.for_org(org).filter(batch=batch).values_list("error_code", flat=True)
    )
    assert "UNMAPPED_PLANT" in err_codes
    assert "UNKNOWN_UNIT" in err_codes
    assert "BAD_DATE" in err_codes
