# Data model

The brief calls the model out as the centerpiece of the submission, and weights it 35%. This document walks through the schema and ties every non-trivial decision back to one of the five stated requirements: multi-tenancy, Scope 1/2/3 categorization, source-of-truth tracking, unit normalization, and audit trail.

## Overview

```
            Organization        <- tenant root
                |
   +------------+------------+--------------------+
   |            |            |                    |
Membership   PlantCode   IngestionBatch    (Airport — global lookup)
(user/org,   (per-org                            
 role)        SAP code         SourceRecord
              mappings)        (immutable raw row,
                               JSONB payload,
                               GIN-indexed)
                                    |
                                    | 1:1
                                    v
                               ActivityRecord
                               (normalized,
                                optimistic-locked,
                                review_state machine)
                                    |
                                    | FK pinned at calc time
                                    v
                               EmissionFactor (versioned, cited)
                                    |
                                    v
                               EmissionCategory (carries the scope)
                                    |
                                    v
                               CanonicalUnit

Cross-cutting:
    ParseError    one per failed row in a batch
    AuditLog      per org, polymorphic target, INSERT-only via DB triggers
```

The shape is deliberate. Raw data is preserved unchanged in `SourceRecord` as JSONB; the normalized projection lives in `ActivityRecord`; the two are joined 1:1. Everything an analyst edits lives on the normalized side. Everything an auditor traces back to lives on the raw side.

## How each requirement is satisfied

### 1. Multi-tenancy

Shared database, shared schema, an `organization_id` column on every tenant-scoped row. Isolation is enforced in two independent layers:

| Layer | Mechanism | What it catches |
|---|---|---|
| Application | `TenantQuerySet.for_org(org)`; `objects.all()` raises `TenantContextMissing` | A developer forgetting to scope a query |
| Database | Postgres RLS policy `(organization_id::text = current_setting('app.current_org_id', true))` with `FORCE ROW LEVEL SECURITY` enabled | Raw SQL, ORM bypass, a future bug in the queryset helper |

The GUC is set per request by `TenantRLSMiddleware`. Anonymous or unscoped requests get an empty string; the policy comparison `organization_id::text = ''` is then FALSE for every real row, so the request sees zero rows. That is the correct failure mode — same outcome as leaving the GUC unset, where `current_setting` returns NULL and the comparison evaluates to NULL.

Why two layers: cross-tenant leakage is the worst-case bug for this product. Either layer alone catches most cases. Both together catch everything that's been thought of. RLS adds one migration (`core/0002_rls_policies`) and one middleware line. It's a small price for the worst class of bug.

### 2. Scope 1/2/3 categorization

Scope is a property of the category, not of the record. An `ActivityRecord` has a `category` FK; the category carries `scope`. There is no `scope` column on `ActivityRecord` to set wrong.

```
ActivityRecord.category  ->  EmissionCategory.scope  (1 | 2 | 3)
```

`ActivityRecord.scope` exists as a read-only Python property that delegates to `category.scope`. Misclassification ("Scope 2 fuel combustion") is a schema-level impossibility: to put a row in Scope 2, it has to be assigned the `purchased_electricity` category — whose default unit is kWh — so a row in litres would already have been rejected at unit conversion.

The seeded categories cover the eight that span the three sources:

| Category code | Scope | Source |
|---|---|---|
| `stationary_fuel_diesel`, `stationary_fuel_petrol`, `mobile_fuel_diesel` | 1 | SAP |
| `purchased_electricity` | 2 | Utility |
| `business_travel_air`, `business_travel_lodging`, `business_travel_ground` | 3 | Travel |
| `purchased_goods_spend` | 3 | SAP (procurement) |

### 3. Source-of-truth tracking

Every `ActivityRecord` has a 1:1 FK to a `SourceRecord` (the raw JSONB payload as parsed). The `SourceRecord` FKs to an `IngestionBatch` (file hash, parser version, uploader, timestamp). Tracing a normalized row to its origin is one join:

```sql
SELECT
  ar.id,
  ar.value, u.code AS unit,
  sr.raw_payload, sr.line_number,
  ib.file_name, ib.file_sha256, ib.parser_version, ib.uploaded_at, ib.uploaded_by_id
FROM activity_record ar
JOIN source_record    sr ON ar.source_record_id = sr.id
JOIN ingestion_batch  ib ON sr.batch_id = ib.id
JOIN canonical_unit   u  ON ar.unit_id = u.id
WHERE ar.id = $1;
```

`SourceRecord` is immutable after insert (enforced by a guard in `save()`). Re-uploading the same bytes is a no-op: `UNIQUE(organization, file_sha256)` on `IngestionBatch` covers the double-click case and the platform-retry case without any extra logic.

`IngestionBatch.parser_version` is stamped at parse time. The intent is that a parser bugfix should be able to replay `SourceRecord` to `ActivityRecord` without re-uploading the file — the raw payload is preserved, and the normalization is deterministic. The `reparse_batch` management command isn't shipped in v1; the `REPARSED` audit action exists in the enum, waiting for it. That deliberate cut is documented in `DECISIONS.md`.

### 4. Unit normalization

```
SourceRecord.raw_payload     - the original unit string is preserved here
ActivityRecord.value         - Decimal(18, 6)
ActivityRecord.unit          - FK to CanonicalUnit (a closed set)
```

The canonical-unit table is deliberately small: `kWh`, `L`, `kg`, `km`, `passenger_km`, `room_nights`, `usd`. Anything else parsed off a source becomes a `ParseError(error_code=UNKNOWN_UNIT)`, and the analyst resolves it by editing the row.

Conversions are explicit per-pair Python functions in `emissions/converters.py`. A test (`test_no_dimension_crossings_registered`) walks the registry and fails if anyone ever adds a mass-to-volume entry. The reasoning for an explicit registry over a general engine like `pint` is in `TRADEOFFS.md` #3.

### 5. Audit trail

`AuditLog` answers "who changed this row, when, and from what to what". Schema:

```
id              bigserial   (monotonic — id ordering equals time ordering)
organization_id FK
actor_user_id   FK, nullable for system actions
request_id      string      matches the X-Request-ID, structlog, and Sentry tag
action          enum        CREATED | UPDATED | APPROVED | FLAGGED | REJECTED
                            | LOCKED | UNLOCKED | REPARSED | LOGGED_IN
target_type     string      e.g. "emissions.ActivityRecord"
target_id       bigint
before          jsonb
after           jsonb
reason          text        required for LOCKED / UNLOCKED
created_at      timestamptz
```

Immutability is enforced in three places, intentionally redundant:

1. **Model layer.** `AuditLog.save()` raises if `pk is not None`. `delete()` always raises.
2. **Database layer.** `BEFORE UPDATE` and `BEFORE DELETE` triggers `RAISE EXCEPTION`. Triggers fire for every role including superuser, which `REVOKE` would not.
3. **Admin layer.** Django admin overrides `has_change_permission` and `has_delete_permission` to return False.

Triggers are the load-bearing layer. In development the app commonly runs as a Postgres superuser, where `REVOKE` on table privileges has no effect. Triggers don't care about role. The test `core/tests/test_audit_immutable.py::test_db_trigger_blocks_raw_update` proves it by attempting a raw SQL UPDATE.

Every mutating request writes one or more rows through `record_change()`, all tagged with the same `request_id`. Stitching a Sentry exception to the rows that changed during the request is a `WHERE request_id = ...` query.

## Optimistic concurrency

`ActivityRecord.version` is an integer, defaulting to 1, incremented on every save. `PATCH /api/activities/:id/` requires `If-Match: <version>`. A mismatch returns 412 with the current state in the response body. The UI renders a diff dialog: "Another analyst changed value from 1,200 to 1,250 — keep yours, take theirs, or cancel."

This is the right correctness shape for an analyst tool where multiple humans review overlapping queues. Pessimistic locking would either degrade UX (rows held while a tab is open) or require connection-state the API layer doesn't want.

## Index strategy

| Index | Purpose |
|---|---|
| `ar_queue_idx (organization, review_state, -activity_date)` | The review queue's hot query: one org, one state, recent first |
| `ar_reporting_idx (organization, category, activity_date)` | Per-category totals on the Overview page |
| `ar_facility_idx (organization, facility_code, activity_date)` | Per-facility filtering on the queue |
| `srec_payload_gin (raw_payload)` | Find raw rows where `plant_code = XYZ` without ETL |
| `srec_batch_line_idx (batch, line_number)` | Detail-page join from a record back to its source row |
| `batch_recent_idx (organization, -uploaded_at)` | Imports tab: recent batches per org |
| `batch_by_source_idx (organization, source_type, -uploaded_at)` | Imports tab filtered to one source (SAP / Utility / Travel) |
| `perr_batch_code_idx (batch, error_code)` | Errors grouped by code on the batch-detail view |
| `auditlog_target_idx (organization, target_type, target_id, -created_at)` | Audit timeline on the record-detail page |
| `auditlog (request_id)` | Trace one request through every row it touched |

Every composite index leads with `organization_id`. The optimizer can then satisfy the tenant filter from the index without an extra scan step. This matters most for the queue query, which is the hottest read in the app.

## What is intentionally not in the model

These are summarized here for context; the full reasoning is in `TRADEOFFS.md`.

- **No general unit-conversion engine.** Every supported pair is an explicit function with a test. The cost is per-pair work for new units; the benefit is that no conversion silently crosses a dimension boundary.
- **No ML anomaly model.** Anomaly hints are rule-based and inspectable, with reasoning strings an auditor can read directly.
- **No connector framework.** The ingestion layer takes bytes. Whether those bytes come from an upload, an S3 drop, or a pulled API is per-customer orchestration, not core schema.
