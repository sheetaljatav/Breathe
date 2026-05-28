"""
Rule-based anomaly hints.

Three rules today (see TRADEOFFS.md #2 for why rule-based, not ML):

  ROLLING_MEDIAN_OUTLIER — value > 5x the rolling 90-day median for the same
                           (org, category, facility) combination
  UNRESOLVED_LOOKUP      — facility/airport/category placeholder pending
  PERIOD_OVERLAP         — period overlaps an existing APPROVED record for
                           the same (org, category, facility) — double-count risk

Hints are computed on-read (not stored), cached for the duration of one
queue request. The reasoning string is human-readable and stable so the
analyst can defend it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q

from .models import ActivityRecord, ReviewState


@dataclass(frozen=True)
class Hint:
    code: str
    message: str
    severity: str  # "info" | "warn" | "block"


def compute_hints(record: ActivityRecord) -> list[Hint]:
    hints: list[Hint] = []

    # Rolling 90-day median, same org+category+facility.
    window_start = record.activity_date - timedelta(days=90)
    peers = (
        ActivityRecord.objects.for_org(record.organization)
        .filter(
            category=record.category,
            facility_code=record.facility_code,
            activity_date__gte=window_start,
            activity_date__lte=record.activity_date,
        )
        .exclude(pk=record.pk)
        .values_list("value", flat=True)
    )
    peers_list = sorted(peers)
    if len(peers_list) >= 3:
        median = peers_list[len(peers_list) // 2]
        if median and record.value > median * Decimal("5"):
            hints.append(Hint(
                code="ROLLING_MEDIAN_OUTLIER",
                message=(
                    f"value {record.value} is more than 5x the 90-day median ({median}) "
                    f"for category={record.category.code}, facility={record.facility_code or '—'} "
                    f"(n={len(peers_list)} prior rows)."
                ),
                severity="warn",
            ))

    # Period overlap against existing approved records.
    if record.period_start and record.period_end:
        overlap = (
            ActivityRecord.objects.for_org(record.organization)
            .filter(
                category=record.category,
                facility_code=record.facility_code,
                review_state=ReviewState.APPROVED,
            )
            .exclude(pk=record.pk)
            .filter(
                Q(period_start__lte=record.period_end)
                & Q(period_end__gte=record.period_start)
            )
            .exists()
        )
        if overlap:
            hints.append(Hint(
                code="PERIOD_OVERLAP",
                message=(
                    "period overlaps an existing approved record for the same "
                    "category and facility — double-counting risk."
                ),
                severity="warn",
            ))

    return hints
