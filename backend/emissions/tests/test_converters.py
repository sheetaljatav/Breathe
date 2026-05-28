"""Per-pair unit conversion correctness. See TRADEOFFS.md #3."""

from __future__ import annotations

from decimal import Decimal

import pytest

from emissions.converters import CONVERSIONS, UnitNotSupported, convert


@pytest.mark.parametrize(
    "raw,canon,value,expected",
    [
        ("kWh", "kWh", "100",  Decimal("100")),
        ("MWh", "kWh", "1.5",  Decimal("1500.0")),
        ("GJ",  "kWh", "1.0",  Decimal("277.7777777778")),
        ("L",   "L",   "42",   Decimal("42")),
        ("m3",  "L",   "0.5",  Decimal("500.0")),
        ("kg",  "kg",  "10",   Decimal("10")),
        ("t",   "kg",  "1.25", Decimal("1250.00")),
        ("TO",  "kg",  "2",    Decimal("2000")),
        ("km",  "km",  "55",   Decimal("55")),
        ("mi",  "km",  "10",   Decimal("16.09344")),
    ],
)
def test_known_conversions(raw, canon, value, expected):
    got = convert(Decimal(value), raw, canon)
    assert got == expected


def test_unknown_raises():
    with pytest.raises(UnitNotSupported):
        convert(Decimal("1"), "psi", "kWh")


def test_no_dimension_crossings_registered():
    """
    Defense-in-depth: enforce that we never accidentally register a conversion
    that crosses dimensions (mass↔volume etc.). This is the contract we make
    in TRADEOFFS.md and the test that proves we kept it.
    """
    dimension_for_unit = {
        "kWh": "energy", "MWh": "energy", "GJ": "energy", "KWH": "energy", "MWH": "energy",
        "L": "volume", "LTR": "volume", "LITER": "volume", "m3": "volume", "M3": "volume",
        "kg": "mass", "KG": "mass", "t": "mass", "T": "mass", "TO": "mass",
        "km": "distance", "KM": "distance", "mi": "distance", "MI": "distance",
    }
    for (raw, canon) in CONVERSIONS.keys():
        d_raw = dimension_for_unit.get(raw)
        d_canon = dimension_for_unit.get(canon)
        assert d_raw is not None and d_canon is not None, (raw, canon)
        assert d_raw == d_canon, (
            f"Cross-dimension conversion registered: {raw}({d_raw}) → {canon}({d_canon}). "
            f"Per TRADEOFFS.md #3 this is not allowed."
        )
