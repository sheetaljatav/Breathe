"""
Celery task: parse_batch.

Orchestration responsibilities, in order:
  1. Load IngestionBatch, pin the org context (RLS).
  2. Read raw bytes from storage.
  3. Build per-org parser context (plant codes for SAP, airports for travel).
  4. Dispatch to the source-specific parser.
  5. In ONE transaction: bulk-insert SourceRecords, then ActivityRecords
     (with factor pinning + emissions calc), then ParseErrors. Update the
     batch row with counts and terminal status.
  6. Delete the original upload bytes (SourceRecord.raw_payload is the
     long-term record).
  7. On any exception, mark the batch FAILED with the error message and
     re-raise so Celery records the failure too.
"""

from __future__ import annotations

import structlog
from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from core.audit import record_change
from core.models import AuditAction
from emissions.calc import pin_factor_and_compute
from emissions.models import (
    ActivityRecord,
    Airport,
    CanonicalUnit,
    EmissionCategory,
    PlantCode,
)

from .models import (
    BatchStatus,
    IngestionBatch,
    ParseError,
    ParseErrorCode,
    SourceRecord,
    SourceType,
)
from .parsers import PARSER_VERSION, get_parser
from .storage import delete as delete_upload
from .storage import read_bytes


log = structlog.get_logger(__name__)


@shared_task(bind=True, name="ingestion.parse_batch", max_retries=2, default_retry_delay=10)
def parse_batch(self, batch_id: int) -> dict:
    """
    Parse an IngestionBatch end-to-end. Returns a small summary dict; the
    full status lives on the IngestionBatch row itself.

    RLS context handling: we set `app.current_org_id` at task entry — BEFORE
    any tenant-scoped query — and clear it in finally. Without this, two
    consecutive tasks on the same worker process would share connection state
    and the second task could see the first task's org context. This matters
    in production where the worker runs as a non-superuser role; in dev with
    a superuser role RLS is bypassed and the leak would be invisible.
    """
    # NB: we deliberately DON'T scope with .for_org here — there's no request
    # context. We load the batch by pk to discover its org, then set the
    # GUC immediately, before any tenant-scoped read.
    batch = IngestionBatch.all_objects.select_related("organization").get(pk=batch_id)
    org = batch.organization

    bound = log.bind(batch_id=batch.id, source_type=batch.source_type, org=org.slug)
    bound.info("parse_batch.start")

    _set_rls_org(org.id)
    try:
        return _run(self, batch, org, bound)
    finally:
        _clear_rls_org()


def _run(self, batch: "IngestionBatch", org, bound) -> dict:
    batch.status = BatchStatus.PARSING
    batch.started_at = timezone.now()
    batch.celery_task_id = self.request.id or ""
    batch.parser_version = PARSER_VERSION
    batch.save(update_fields=["status", "started_at", "celery_task_id", "parser_version"])

    try:
        data = read_bytes(batch.id)
    except FileNotFoundError as e:
        return _fail(batch, f"Upload file missing: {e}")

    parser = get_parser(batch.source_type, file_name=batch.file_name)
    context = _build_context(org, batch.source_type)

    try:
        result = parser.parse(data, context=context)
    except Exception as e:  # noqa: BLE001
        bound.exception("parser.exception")
        return _fail(batch, f"Parser raised: {e}")

    try:
        with transaction.atomic():
            ok, failed = _persist(batch, result)
    except Exception as e:  # noqa: BLE001
        bound.exception("persist.exception")
        return _fail(batch, f"Persist failed: {e}")

    batch.rows_total = ok + failed
    batch.rows_ok = ok
    batch.rows_failed = failed
    batch.status = BatchStatus.COMPLETE
    batch.finished_at = timezone.now()
    batch.save(update_fields=["rows_total", "rows_ok", "rows_failed",
                              "status", "finished_at"])

    # The structured payload survives on SourceRecord; we don't need the
    # original file bytes anymore.
    delete_upload(batch.id)

    record_change(
        organization=org, actor=batch.uploaded_by,
        action=AuditAction.CREATED, target=batch,
        after={"rows_ok": ok, "rows_failed": failed},
    )

    bound.info("parse_batch.complete", rows_ok=ok, rows_failed=failed)
    return {"batch_id": batch.id, "ok": ok, "failed": failed}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_context(org, source_type: str) -> dict:
    if source_type == SourceType.SAP:
        return {"plant_codes": set(
            PlantCode.objects.filter(organization=org).values_list("code", flat=True)
        )}
    if source_type == SourceType.TRAVEL:
        return {"airports": {
            a.iata: (float(a.latitude), float(a.longitude))
            for a in Airport.objects.all()
        }}
    return {}


def _set_rls_org(org_id: int) -> None:
    """Set the per-request org GUC on the current DB connection."""
    from django.conf import settings
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)",
                    [settings.RLS_ORG_GUC, str(org_id)])


def _clear_rls_org() -> None:
    """Reset the GUC so the next task on this connection starts clean."""
    from django.conf import settings
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, '', false)", [settings.RLS_ORG_GUC])


def _persist(batch: IngestionBatch, result) -> tuple[int, int]:
    """Bulk-insert source records, then activity drafts + errors. Returns (ok, failed)."""

    # 1. SourceRecords. We need their PKs to FK from ActivityRecords; bulk_create
    #    sets pks on the returned list when the DB supports it (Postgres does).
    import hashlib
    import json
    src_rows = [
        SourceRecord(
            organization=batch.organization, batch=batch,
            line_number=r.line_number, raw_payload=r.raw_payload,
            raw_hash=hashlib.sha256(
                json.dumps(r.raw_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        for r in result.records
    ]
    SourceRecord.objects.bulk_create(src_rows)
    by_line = {row.line_number: row for row in src_rows}

    # 2. Reference lookups in one query each.
    cats = {c.code: c for c in EmissionCategory.objects.filter(
        code__in={d.category_code for d in result.drafts})}
    units = {u.code: u for u in CanonicalUnit.objects.filter(
        code__in={d.canonical_unit_code for d in result.drafts})}

    # 3. ActivityRecords. Build, pin factor, compute, then bulk insert.
    ar_rows: list[ActivityRecord] = []
    for d in result.drafts:
        cat = cats.get(d.category_code)
        unit = units.get(d.canonical_unit_code)
        if cat is None or unit is None:
            # Synthesize a ParseError so the issue surfaces, instead of silently
            # dropping the row. The parser produced a draft because *its* world
            # (prefix + canonical unit) said the row was valid; the persistence
            # layer is rejecting it because reference data is missing in this
            # org. Treating it as an error makes the gap visible to the analyst.
            result.errors.append(_ParseErrorShim(
                line_number=d.line_number,
                error_code=ParseErrorCode.UNKNOWN_CATEGORY if cat is None else ParseErrorCode.UNKNOWN_UNIT,
                message=f"category={d.category_code} unit={d.canonical_unit_code} not in reference data",
            ))
            continue
        ar = ActivityRecord(
            organization=batch.organization,
            source_record=by_line.get(d.line_number),
            category=cat, unit=unit,
            activity_date=d.activity_date,
            period_start=d.period_start, period_end=d.period_end,
            value=d.value, facility_code=d.facility_code, notes=d.notes,
        )
        # Region defaults to "global"; SAP rows with a plant in DE/US would
        # benefit from region-specific pinning — left for v2.
        pin_factor_and_compute(ar)
        ar_rows.append(ar)
    ActivityRecord.objects.bulk_create(ar_rows)

    # 4. ParseErrors
    err_rows = [
        ParseError(
            organization=batch.organization, batch=batch,
            line_number=e.line_number, error_code=e.error_code,
            field_path=getattr(e, "field_path", "") or "",
            message=e.message, raw_excerpt=getattr(e, "raw_excerpt", None),
        )
        for e in result.errors
    ]
    ParseError.objects.bulk_create(err_rows)

    return (len(ar_rows), len(err_rows))


class _ParseErrorShim:
    """Lightweight stand-in for ParseErrorShape from inside _persist; same field names."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.field_path = kw.get("field_path", "")
        self.raw_excerpt = kw.get("raw_excerpt")


def _fail(batch: IngestionBatch, message: str) -> dict:
    batch.status = BatchStatus.FAILED
    batch.error_summary = message
    batch.finished_at = timezone.now()
    batch.save(update_fields=["status", "error_summary", "finished_at"])
    delete_upload(batch.id)
    return {"batch_id": batch.id, "status": "failed", "error": message}
