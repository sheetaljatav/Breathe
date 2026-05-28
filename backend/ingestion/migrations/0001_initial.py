"""
Hand-written initial migration for ingestion. See core/migrations/0001_initial.py
for the rationale (avoiding the makemigrations chicken-and-egg with core's
hand-written 0002 and 0003).
"""

import django.contrib.postgres.indexes
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.tenancy


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IngestionBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(choices=[
                    ("sap", "SAP (fuel/procurement)"),
                    ("utility", "Utility (electricity)"),
                    ("travel", "Corporate travel"),
                ], max_length=16)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("file_name", models.CharField(max_length=255)),
                ("file_sha256", models.CharField(max_length=64)),
                ("file_size_bytes", models.BigIntegerField()),
                ("parser_version", models.CharField(max_length=32)),
                ("status", models.CharField(choices=[
                    ("queued", "Queued"), ("parsing", "Parsing"),
                    ("complete", "Complete"), ("failed", "Failed"),
                ], default="queued", max_length=16)),
                ("rows_total", models.IntegerField(default=0)),
                ("rows_ok", models.IntegerField(default=0)),
                ("rows_failed", models.IntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=64)),
                ("error_summary", models.TextField(blank=True)),
                ("organization", models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="core.organization")),
                ("uploaded_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "ingestion_batch",
                "ordering": ("-uploaded_at",),
                "unique_together": {("organization", "file_sha256")},
            },
            managers=[("objects", core.tenancy.TenantManager())],
        ),
        migrations.AddIndex(
            model_name="ingestionbatch",
            index=models.Index(fields=["organization", "-uploaded_at"], name="batch_recent_idx"),
        ),
        migrations.AddIndex(
            model_name="ingestionbatch",
            index=models.Index(
                fields=["organization", "source_type", "-uploaded_at"],
                name="batch_by_source_idx"),
        ),
        migrations.CreateModel(
            name="SourceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_number", models.IntegerField()),
                ("raw_payload", models.JSONField()),
                ("raw_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="records", to="ingestion.ingestionbatch")),
                ("organization", models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="core.organization")),
            ],
            options={
                "db_table": "source_record",
                "unique_together": {("batch", "line_number")},
            },
            managers=[("objects", core.tenancy.TenantManager())],
        ),
        migrations.AddIndex(
            model_name="sourcerecord",
            index=models.Index(fields=["batch", "line_number"], name="srec_batch_line_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcerecord",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["raw_payload"], name="srec_payload_gin"),
        ),
        migrations.CreateModel(
            name="ParseError",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_number", models.IntegerField()),
                ("error_code", models.CharField(choices=[
                    ("UNKNOWN_UNIT", "Unit not in canonical set"),
                    ("MISSING_FIELD", "Required field absent"),
                    ("UNMAPPED_PLANT", "Plant code has no facility mapping"),
                    ("UNRESOLVABLE_AIRPORT", "Airport pair not in lookup"),
                    ("BAD_DATE", "Date could not be parsed"),
                    ("BAD_NUMBER", "Numeric value malformed"),
                    ("UNKNOWN_CATEGORY", "No emission category match"),
                    ("SCANNED_PDF_NEEDS_MANUAL_ENTRY", "Scanned PDF — manual entry"),
                ], max_length=48)),
                ("field_path", models.CharField(blank=True, max_length=128)),
                ("message", models.TextField()),
                ("raw_excerpt", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="errors", to="ingestion.ingestionbatch")),
                ("organization", models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="core.organization")),
            ],
            options={"db_table": "parse_error"},
            managers=[("objects", core.tenancy.TenantManager())],
        ),
        migrations.AddIndex(
            model_name="parseerror",
            index=models.Index(fields=["batch", "error_code"], name="perr_batch_code_idx"),
        ),
    ]
