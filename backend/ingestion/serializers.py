from __future__ import annotations

from rest_framework import serializers

from .models import IngestionBatch, ParseError


class ParseErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParseError
        fields = ("id", "line_number", "error_code", "field_path", "message", "raw_excerpt")


class IngestionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionBatch
        fields = (
            "id", "source_type", "file_name", "file_sha256", "file_size_bytes",
            "parser_version", "status", "rows_total", "rows_ok", "rows_failed",
            "uploaded_at", "started_at", "finished_at", "error_summary",
        )


class IngestionBatchDetailSerializer(IngestionBatchSerializer):
    errors = ParseErrorSerializer(many=True, read_only=True)

    class Meta(IngestionBatchSerializer.Meta):
        fields = IngestionBatchSerializer.Meta.fields + ("errors",)
