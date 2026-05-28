from __future__ import annotations

from rest_framework import serializers

from .models import (
    ActivityRecord,
    Airport,
    CanonicalUnit,
    EmissionCategory,
    EmissionFactor,
    PlantCode,
)


class CanonicalUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CanonicalUnit
        fields = ("id", "code", "label", "dimension")


class EmissionCategorySerializer(serializers.ModelSerializer):
    default_unit = CanonicalUnitSerializer(read_only=True)

    class Meta:
        model = EmissionCategory
        fields = ("id", "code", "label", "scope", "default_unit", "ghg_protocol_ref")


class EmissionFactorSerializer(serializers.ModelSerializer):
    category = EmissionCategorySerializer(read_only=True)
    unit = CanonicalUnitSerializer(read_only=True)

    class Meta:
        model = EmissionFactor
        fields = ("id", "category", "region", "year", "unit", "kg_co2e_per_unit",
                  "source", "effective_from", "effective_to")


class PlantCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantCode
        fields = ("id", "code", "facility_name", "country")


class AirportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Airport
        fields = ("iata", "name", "city", "country", "latitude", "longitude")


class ActivityRecordSerializer(serializers.ModelSerializer):
    category = EmissionCategorySerializer(read_only=True)
    unit = CanonicalUnitSerializer(read_only=True)
    emission_factor = EmissionFactorSerializer(read_only=True)
    scope = serializers.IntegerField(read_only=True)
    source_type = serializers.SerializerMethodField()
    batch_id = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = (
            "id", "scope", "category", "activity_date", "period_start", "period_end",
            "value", "unit", "emission_factor", "emissions_kg_co2e",
            "facility_code", "notes",
            "review_state", "reviewed_by", "reviewed_at", "locked_at",
            "version", "created_at", "updated_at",
            "source_type", "batch_id",
        )

    def get_source_type(self, obj):
        if obj.source_record_id and obj.source_record:
            return obj.source_record.batch.source_type
        return None

    def get_batch_id(self, obj):
        return obj.source_record.batch_id if obj.source_record_id else None


class ActivityRecordEditSerializer(serializers.ModelSerializer):
    """Only the fields an analyst is allowed to edit. Version is required for If-Match."""

    class Meta:
        model = ActivityRecord
        fields = ("value", "unit", "category", "activity_date",
                  "period_start", "period_end", "facility_code", "notes")
