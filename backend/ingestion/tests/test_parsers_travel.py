"""Golden tests for the Concur-shape travel JSON parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ingestion.parsers.travel import TravelParser


SAMPLE = (
    Path(__file__).resolve().parents[3]
    / "samples" / "concur_reporting_v4_trip_response.json"
)


# Mirror the relevant subset of seed_demo's airport fixture.
AIRPORTS = {
    "SFO": (37.6213, -122.3790),
    "ORD": (41.9742,  -87.9073),
    "JFK": (40.6413,  -73.7781),
    "LHR": (51.4700,   -0.4543),
    "FRA": (50.0379,    8.5622),
    "MUC": (48.3538,   11.7861),
}


def test_travel_parses_sample_with_distance_fallback():
    data = SAMPLE.read_bytes()
    result = TravelParser().parse(data, context={"airports": AIRPORTS})

    # 3 trips with (5 + 3 + 4) = 12 segments
    assert len(result.records) == 12

    # The LHR→XYZ segment should produce UNRESOLVABLE_AIRPORT.
    bad = [e for e in result.errors if e.error_code == "UNRESOLVABLE_AIRPORT"]
    assert len(bad) == 1

    # The SFO→ORD segment ships an explicit distance (2964 km) — should be preserved.
    sfo_ord = next(
        d for d in result.drafts
        if d.category_code == "business_travel_air" and "SFO->ORD" in d.notes
    )
    assert sfo_ord.value == Decimal("2964.000")
    assert sfo_ord.canonical_unit_code == "passenger_km"

    # ORD→SFO has null distance; we computed it. Should be > 0 and close to 2964.
    ord_sfo = next(
        d for d in result.drafts
        if d.category_code == "business_travel_air" and "ORD->SFO" in d.notes
    )
    assert ord_sfo.value > Decimal("2900")
    assert ord_sfo.value < Decimal("3050")

    # Lodging segment from trip 1: 3 nights at MAR-ORD-DT
    nights = [d for d in result.drafts if d.category_code == "business_travel_lodging"]
    assert any(d.value == Decimal("3") for d in nights)

    # Car segment with explicit distance
    cars = [d for d in result.drafts if d.category_code == "business_travel_ground"]
    assert any(d.value == Decimal("28") for d in cars)


def test_invalid_json_yields_single_error():
    result = TravelParser().parse(b"not json", context={"airports": AIRPORTS})
    assert len(result.records) == 0
    assert len(result.errors) == 1
