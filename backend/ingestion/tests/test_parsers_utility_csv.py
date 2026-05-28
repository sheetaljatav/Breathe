"""Golden tests for the utility CSV parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ingestion.parsers.utility_csv import UtilityCSVParser


SAMPLE = (
    Path(__file__).resolve().parents[3]
    / "samples" / "utility_portal_export_meter_xyz.csv"
)


def test_utility_csv_parses_sample():
    data = SAMPLE.read_bytes()
    result = UtilityCSVParser().parse(data)
    assert len(result.records) == 11
    assert len(result.drafts) == 11   # all rows are valid in the sample
    assert len(result.errors) == 0

    # The MWh row should normalize to kWh (12.1 * 1000 = 12100).
    mwh_row = next(d for d in result.drafts if d.activity_date == date(2026, 4, 30))
    assert mwh_row.value == Decimal("12100.0")
    assert mwh_row.canonical_unit_code == "kWh"
    assert mwh_row.period_start == date(2026, 4, 1)


def test_utility_csv_flags_unknown_unit():
    data = (
        b"meter_id,service_address,rate_class,billing_period_start,"
        b"billing_period_end,consumption,consumption_unit\n"
        b"M-1,addr,GS,2026-01-01,2026-01-31,1000,therms\n"
    )
    result = UtilityCSVParser().parse(data)
    assert len(result.records) == 1
    assert len(result.drafts) == 0
    assert result.errors[0].error_code == "UNKNOWN_UNIT"
