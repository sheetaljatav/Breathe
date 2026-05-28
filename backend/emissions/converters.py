"""
Explicit per-pair unit conversions.

NO general unit-conversion engine here. Every supported (raw_unit, canonical_unit)
conversion is one function in this file. See TRADEOFFS.md #3 for the reasoning.

Add a new conversion:
  1. Write the function with type Decimal -> Decimal.
  2. Register it in CONVERSIONS.
  3. Add a test in tests/test_converters.py with a known-good number.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable


def kwh_from_mwh(v: Decimal) -> Decimal:
    return v * Decimal("1000")


def kwh_from_kwh(v: Decimal) -> Decimal:
    return v


def kwh_from_gj(v: Decimal) -> Decimal:
    # 1 GJ = 277.777... kWh
    return v * Decimal("277.7777777778")


def l_from_l(v: Decimal) -> Decimal:
    return v


def l_from_m3(v: Decimal) -> Decimal:
    return v * Decimal("1000")


def kg_from_kg(v: Decimal) -> Decimal:
    return v


def kg_from_t(v: Decimal) -> Decimal:
    return v * Decimal("1000")


def km_from_km(v: Decimal) -> Decimal:
    return v


def km_from_mi(v: Decimal) -> Decimal:
    return v * Decimal("1.609344")


# (raw_unit, canonical_unit) -> conversion function
CONVERSIONS: dict[tuple[str, str], Callable[[Decimal], Decimal]] = {
    ("kWh", "kWh"): kwh_from_kwh,
    ("KWH", "kWh"): kwh_from_kwh,
    ("MWh", "kWh"): kwh_from_mwh,
    ("MWH", "kWh"): kwh_from_mwh,
    ("GJ",  "kWh"): kwh_from_gj,
    ("L",   "L"):   l_from_l,
    ("LTR", "L"):   l_from_l,
    ("LITER", "L"): l_from_l,
    ("m3",  "L"):   l_from_m3,
    ("M3",  "L"):   l_from_m3,
    ("kg",  "kg"):  kg_from_kg,
    ("KG",  "kg"):  kg_from_kg,
    ("t",   "kg"):  kg_from_t,
    ("T",   "kg"):  kg_from_t,
    ("TO",  "kg"):  kg_from_t,        # SAP often uses "TO" for metric tonne
    ("km",  "km"):  km_from_km,
    ("KM",  "km"):  km_from_km,
    ("mi",  "km"):  km_from_mi,
    ("MI",  "km"):  km_from_mi,
}


class UnitNotSupported(Exception):
    """Raised when (raw_unit, canonical_unit) isn't in CONVERSIONS."""


def convert(value: Decimal, raw_unit: str, canonical_unit: str) -> Decimal:
    fn = CONVERSIONS.get((raw_unit, canonical_unit))
    if fn is None:
        raise UnitNotSupported(
            f"No registered conversion from {raw_unit!r} to {canonical_unit!r}. "
            f"Add one to emissions/converters.py if appropriate."
        )
    return fn(value)
