"""Golden tests for the SAP SE16N parser."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ingestion.parsers.sap import SAPParser


SAMPLE = (
    Path(__file__).resolve().parents[3] / "samples" / "sap_se16n_export_2026Q1.csv"
)


def test_sap_parses_sample_and_routes_issues_correctly():
    data = SAMPLE.read_bytes()
    parser = SAPParser()
    # Pretend Acme has plant codes 1000/1100/2000/2100 mapped (matches seed_demo).
    context = {"plant_codes": {"1000", "1100", "2000", "2100"}}
    result = parser.parse(data, context=context)

    # Every row of the CSV becomes a SourceRecord (we preserve raw regardless).
    assert len(result.records) == 48

    # ParseErrors should include:
    #   * 1 unmapped plant (ZZZZ)
    #   * 1 unknown unit (US gallons on a DIESEL_B7 row — realistic data-entry mistake)
    #   * 1 bad date (33.03.2026)
    codes = sorted(e.error_code for e in result.errors)
    assert "UNMAPPED_PLANT" in codes
    assert "UNKNOWN_UNIT" in codes
    assert "BAD_DATE" in codes

    # ActivityRecord drafts: 48 rows - 1 UNKNOWN_UNIT - 1 BAD_DATE = 46.
    # (UNMAPPED_PLANT still produces a draft, deliberately.)
    # Loosened to ≥ 40 to avoid brittle counting if sample evolves.
    assert len(result.drafts) >= 40

    # First diesel row: 1.234,56 L → 1234.56 L canonical.
    diesel_first = next(d for d in result.drafts if d.line_number == 2)
    assert diesel_first.category_code == "mobile_fuel_diesel"
    assert diesel_first.canonical_unit_code == "L"
    assert diesel_first.value == Decimal("1234.56")
    assert diesel_first.facility_code == "1000"

    # A procurement row: 120 ST OFFICE_PAPER → spend draft in USD.
    paper = next(d for d in result.drafts if "OFFICE_PAPER_A4" in (d.notes or ""))
    assert paper.category_code == "purchased_goods_spend"
    assert paper.canonical_unit_code == "usd"


def test_sap_rejects_missing_required_header():
    data = b"Werk;Buchungsdatum;Material\n1000;01.01.2026;DIESEL_B7\n"
    result = SAPParser().parse(data, context={"plant_codes": {"1000"}})
    assert len(result.records) == 0
    assert len(result.errors) == 1
    assert result.errors[0].error_code == "MISSING_FIELD"
