"""
Raw-layer ingestion models.

Three tables, each with one job:

  IngestionBatch  — one upload event. The provenance root. UNIQUE on
                    (organization, file_sha256) gives us idempotent re-uploads
                    without any application-layer dedup logic.

  SourceRecord    — one row from the source file, exactly as parsed (a JSONB
                    payload). IMMUTABLE after insert — the only edits live on
                    ActivityRecord. Auditors trace claims back to this row.

  ParseError      — a row that didn't yield an ActivityRecord. Has a structured
                    error_code so the analyst UI can group + show fixes.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from core.tenancy import TenantModel


class SourceType(models.TextChoices):
    SAP = "sap", "SAP (fuel/procurement)"
    UTILITY = "utility", "Utility (electricity)"
    TRAVEL = "travel", "Corporate travel"


class BatchStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PARSING = "parsing", "Parsing"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class IngestionBatch(TenantModel):
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Idempotency: re-uploading the same bytes returns the existing batch.
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64)
    file_size_bytes = models.BigIntegerField()

    # Provenance for replay: parser version lets us regenerate ActivityRecord
    # rows from SourceRecord rows if we fix a parser bug, without re-uploading.
    parser_version = models.CharField(max_length=32)

    status = models.CharField(
        max_length=16, choices=BatchStatus.choices, default=BatchStatus.QUEUED
    )
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    celery_task_id = models.CharField(max_length=64, blank=True)
    error_summary = models.TextField(blank=True)

    class Meta:
        db_table = "ingestion_batch"
        unique_together = [("organization", "file_sha256")]
        indexes = [
            models.Index(
                fields=["organization", "-uploaded_at"],
                name="batch_recent_idx",
            ),
            models.Index(
                fields=["organization", "source_type", "-uploaded_at"],
                name="batch_by_source_idx",
            ),
        ]
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return f"{self.source_type}:{self.file_name} ({self.status})"


class SourceRecord(TenantModel):
    """
    A single row from a source file, as parsed into a normalized JSON envelope.
    Immutable. The raw bytes of the file live (briefly) in object storage during
    parsing; what survives long-term is this structured payload.
    """

    batch = models.ForeignKey(
        IngestionBatch, on_delete=models.CASCADE, related_name="records"
    )
    line_number = models.IntegerField()
    raw_payload = models.JSONField()
    raw_hash = models.CharField(max_length=64)   # sha256 of payload JSON
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_record"
        indexes = [
            models.Index(fields=["batch", "line_number"], name="srec_batch_line_idx"),
            GinIndex(fields=["raw_payload"], name="srec_payload_gin"),
        ]
        unique_together = [("batch", "line_number")]

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise PermissionError(
                "SourceRecord is immutable; create a new IngestionBatch to replace."
            )
        super().save(*args, **kwargs)


class ParseErrorCode(models.TextChoices):
    UNKNOWN_UNIT = "UNKNOWN_UNIT", "Unit not in canonical set"
    MISSING_FIELD = "MISSING_FIELD", "Required field absent"
    UNMAPPED_PLANT = "UNMAPPED_PLANT", "Plant code has no facility mapping"
    UNRESOLVABLE_AIRPORT = "UNRESOLVABLE_AIRPORT", "Airport pair not in lookup"
    BAD_DATE = "BAD_DATE", "Date could not be parsed"
    BAD_NUMBER = "BAD_NUMBER", "Numeric value malformed"
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY", "No emission category match"
    SCANNED_PDF = "SCANNED_PDF_NEEDS_MANUAL_ENTRY", "Scanned PDF — manual entry"


class ParseError(TenantModel):
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="errors")
    line_number = models.IntegerField()
    error_code = models.CharField(max_length=48, choices=ParseErrorCode.choices)
    field_path = models.CharField(max_length=128, blank=True)
    message = models.TextField()
    raw_excerpt = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parse_error"
        indexes = [
            models.Index(fields=["batch", "error_code"], name="perr_batch_code_idx"),
        ]
