"""
Pin an emission factor to an ActivityRecord and compute kg CO2e.

This is the one place where factor lookup happens. Lookup order:
  1. exact match on (category, region, year, unit)
  2. fall back to year-1 within the same category/region/unit
  3. fall back to region='global' if region-specific doesn't exist

If no factor exists, we leave emission_factor and emissions_kg_co2e NULL
on the record — the analyst sees an unflagged "no factor" indicator and
can pick one manually. We don't ever guess.
"""

from __future__ import annotations

from decimal import Decimal

from .models import ActivityRecord, EmissionFactor


def pin_factor_and_compute(record: ActivityRecord, *, region: str = "global") -> bool:
    """Returns True if a factor was pinned, False if no match exists."""
    factor = (
        EmissionFactor.objects.filter(
            category=record.category,
            unit=record.unit,
            year=record.activity_date.year,
            region=region,
        )
        .first()
        or EmissionFactor.objects.filter(
            category=record.category,
            unit=record.unit,
            year=record.activity_date.year - 1,
            region=region,
        )
        .first()
        or EmissionFactor.objects.filter(
            category=record.category,
            unit=record.unit,
            year=record.activity_date.year,
            region="global",
        )
        .first()
    )
    if factor is None:
        return False
    record.emission_factor = factor
    record.emissions_kg_co2e = (record.value * factor.kg_co2e_per_unit).quantize(Decimal("0.001"))
    return True
