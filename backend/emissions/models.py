"""
Normalized + review-layer models.

The split here is deliberate:

  Reference data (shared across orgs, edited only via fixtures or admin):
    CanonicalUnit, EmissionCategory, EmissionFactor, PlantCode, Airport.

  Per-tenant data:
    ActivityRecord — the normalized rows that analysts review and approve.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.tenancy import TenantModel


# ---------------------------------------------------------------------------
# Reference data (NOT tenant-scoped — these are global/seeded).
# ---------------------------------------------------------------------------


class UnitDimension(models.TextChoices):
    ENERGY = "energy", "Energy"
    VOLUME = "volume", "Volume"
    MASS = "mass", "Mass"
    DISTANCE = "distance", "Distance"
    PASSENGER_DISTANCE = "passenger_distance", "Passenger-distance"
    COUNT = "count", "Count"
    CURRENCY = "currency", "Currency"


class CanonicalUnit(models.Model):
    """
    Our canonical unit set. Deliberately small and deliberately closed:
    anything outside this set becomes a ParseError, not a silent conversion.

    See TRADEOFFS.md for why we do not use a general unit-conversion engine.
    """

    code = models.CharField(max_length=24, unique=True)
    label = models.CharField(max_length=64)
    dimension = models.CharField(max_length=24, choices=UnitDimension.choices)

    class Meta:
        db_table = "canonical_unit"
        ordering = ("dimension", "code")

    def __str__(self) -> str:
        return self.code


class Scope(models.IntegerChoices):
    SCOPE_1 = 1, "Scope 1 (direct)"
    SCOPE_2 = 2, "Scope 2 (purchased energy)"
    SCOPE_3 = 3, "Scope 3 (indirect / value chain)"


class EmissionCategory(models.Model):
    """
    A GHG Protocol activity category. Scope is a property OF the category,
    never set independently on an ActivityRecord — this prevents the
    "Scope 2 fuel combustion" misclassification at the schema level.
    """

    code = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    scope = models.IntegerField(choices=Scope.choices)
    default_unit = models.ForeignKey(CanonicalUnit, on_delete=models.PROTECT, related_name="+")
    ghg_protocol_ref = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "emission_category"
        ordering = ("scope", "code")

    def __str__(self) -> str:
        return f"S{self.scope}/{self.code}"


class EmissionFactor(models.Model):
    """
    Versioned emission factor. Pinned to ActivityRecord at calc time, so
    when DEFRA publishes 2027 numbers next year, last year's calculations
    don't drift.

    UNIQUE (category, region, year, unit) — one factor per cell. New factor
    issuances create new rows (with effective_from = today) rather than
    UPDATEing the prior row.
    """

    category = models.ForeignKey(EmissionCategory, on_delete=models.PROTECT, related_name="factors")
    region = models.CharField(max_length=16)               # ISO-3166 alpha-2 or "global"
    year = models.IntegerField()
    unit = models.ForeignKey(CanonicalUnit, on_delete=models.PROTECT, related_name="+")
    kg_co2e_per_unit = models.DecimalField(max_digits=18, decimal_places=6)
    source = models.CharField(max_length=128)              # "DEFRA 2024", "EPA eGRID 2023 RFC"
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "emission_factor"
        unique_together = [("category", "region", "year", "unit")]
        indexes = [models.Index(fields=["category", "region", "year"])]
        ordering = ("category", "region", "-year")

    def __str__(self) -> str:
        return f"{self.category.code}/{self.region}/{self.year}: {self.kg_co2e_per_unit} kgCO2e per {self.unit.code}"


class PlantCode(models.Model):
    """SAP `Werk` → facility name + country. Tenant-scoped: each org has its own mapping."""

    organization = models.ForeignKey("core.Organization", on_delete=models.CASCADE, related_name="plant_codes")
    code = models.CharField(max_length=8)
    facility_name = models.CharField(max_length=200)
    country = models.CharField(max_length=2)               # ISO-3166 alpha-2

    class Meta:
        db_table = "plant_code"
        unique_together = [("organization", "code")]


class Airport(models.Model):
    """
    Minimal airport reference: IATA → lat/lon for great-circle distance.
    Global, not tenant-scoped (airports are airports).
    """

    iata = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=128)
    city = models.CharField(max_length=64)
    country = models.CharField(max_length=2)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        db_table = "airport"


# ---------------------------------------------------------------------------
# Per-tenant: the heart of the review loop.
# ---------------------------------------------------------------------------


class ReviewState(models.TextChoices):
    PENDING = "pending", "Pending review"
    FLAGGED = "flagged", "Flagged"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    LOCKED = "locked", "Locked for audit"


class ActivityRecord(TenantModel):
    """
    A normalized emissions activity, derived from exactly one SourceRecord.

    Why fields are shaped this way:
      * `value` + `unit` together carry the canonical measurement. Any other
        unit observed on the raw side becomes a ParseError.
      * `period_start` / `period_end` capture billing periods that don't align
        to calendar months (typical for utility data) — we don't force them.
      * `emission_factor` is pinned at calc time. Recalculating with a fresher
        factor is an explicit operation that creates audit entries.
      * `version` enables optimistic concurrency on the PATCH endpoint via the
        If-Match header. Two analysts saving the same row → second one gets
        412 + the current state.
    """

    source_record = models.OneToOneField(
        "ingestion.SourceRecord",
        on_delete=models.PROTECT,
        related_name="activity",
        null=True, blank=True,
    )
    category = models.ForeignKey(EmissionCategory, on_delete=models.PROTECT, related_name="+")
    activity_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    value = models.DecimalField(max_digits=18, decimal_places=6)
    unit = models.ForeignKey(CanonicalUnit, on_delete=models.PROTECT, related_name="+")

    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, related_name="+",
        null=True, blank=True,
    )
    emissions_kg_co2e = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True
    )

    facility_code = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    review_state = models.CharField(
        max_length=16, choices=ReviewState.choices, default=ReviewState.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    # Optimistic concurrency. Every save() that isn't a creation increments this.
    version = models.IntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "activity_record"
        indexes = [
            models.Index(
                fields=["organization", "review_state", "-activity_date"],
                name="ar_queue_idx",
            ),
            models.Index(
                fields=["organization", "category", "activity_date"],
                name="ar_reporting_idx",
            ),
            models.Index(
                fields=["organization", "facility_code", "activity_date"],
                name="ar_facility_idx",
            ),
        ]
        ordering = ("-activity_date", "-id")

    # Scope is derived from category. Never a settable field on this model.
    @property
    def scope(self) -> int:
        return self.category.scope

    def save(self, *args, **kwargs) -> None:
        if self.pk and self.review_state == ReviewState.LOCKED and not kwargs.pop("_unlock", False):
            # Refuse mutation of locked rows at the model layer too.
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("ActivityRecord is locked for audit; unlock first (admin only).")
        super().save(*args, **kwargs)
