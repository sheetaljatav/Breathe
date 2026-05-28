# Local testing flow

> Internal document. Not part of the submission. Walk through it top to bottom before pushing or deploying.

Goal: catch regressions and gaps in the localhost build before the grader sees the deployed version. A clean run should take about 25 minutes.

---

## 0. Pre-flight (2 min)

Three terminals running, plus a browser tab.

| Check | Command | Expected |
|---|---|---|
| Backend up | `curl http://127.0.0.1:8000/healthz` | `{"status": "ok"}` |
| DB + Redis reachable | `curl http://127.0.0.1:8000/readyz` | `{"db": true, "redis": true}` |
| Worker up | Look at the Celery terminal | Last line: `celery@<host> ready.` |
| Frontend up | Open `http://localhost:5173` | Sign-in page renders with 3 demo accounts |
| Sample PDF exists | `ls samples/utility_bill_acme_facility_03_2026.pdf` | File present (otherwise: `python samples/_generate_utility_pdf.py`) |

If any of these fail, stop and fix before continuing.

---

## 1. Auth (3 min)

- [ ] Click the `analyst@acme.test` row on login → form prefilled → Sign in → land on Overview.
- [ ] Sign out from the top-right menu → redirected to sign-in.
- [ ] Try `analyst@acme.test` with password `wrong` → 401 / "Invalid credentials" toast (not 500).
- [ ] Try a non-existent email → same 401 (the error message should NOT leak whether the email exists).
- [ ] Sign in again as `analyst@acme.test`.

---

## 2. SAP ingestion (4 min)

- [ ] **Imports → SAP** tab → drop `samples/sap_se16n_export_2026Q1.csv`.
- [ ] Endpoint returns 202 with a `batch_id`. Status chip starts at `queued`.
- [ ] Within ~2s the chip moves to `parsing`, then `complete`.
- [ ] Batch detail shows **48 rows total**, **3 errors**:
    - `UNMAPPED_PLANT` for `ZZZZ`
    - `UNKNOWN_UNIT` for `GAL`
    - `BAD_DATE` for `33.03.2026`
- [ ] The 45 successful rows appear in the queue with `review_state = parsed` (or `flagged` for the outlier).
- [ ] The row with quantity `15.450,00 L` carries a `ROLLING_MEDIAN_OUTLIER` anomaly hint.
- [ ] German decimal `15.450,00` was parsed as `15450.00` (Decimal), not `15.45`.
- [ ] German date `19.03.2026` parsed as `2026-03-19`.
- [ ] **Re-drop the same file.** Response shows `deduped: true` (or "Already imported — batch #N"). No second batch row appears in the Imports list.

If parsing stays `queued` forever: worker can't reach Redis. Check `REDIS_URL` and the Celery terminal output.

---

## 3. Utility CSV (2 min)

- [ ] **Imports → Utility** tab → drop `samples/utility_portal_export_meter_xyz.csv`.
- [ ] Batch goes `queued → parsing → complete`. 11 rows parsed, 0 errors.
- [ ] The MWh row (`12.1 MWh`) shows up in the queue with a normalized value of `12100` and unit `kWh`.
- [ ] The 1,075,000 kWh row carries `ROLLING_MEDIAN_OUTLIER` (12× the median).
- [ ] All 11 rows have `category = purchased_electricity` and `scope = 2`.

---

## 4. Utility PDF (2 min)

- [ ] **Imports → Utility** tab → drop `samples/utility_bill_acme_facility_03_2026.pdf`.
- [ ] Batch processes. 1 record.
- [ ] Open the record → all five extracted fields visible: account, service address, meter ID, billing period, consumption.
- [ ] `consumption_kwh` is non-zero and matches the bill's printed value.

If extraction errors out: regenerate the PDF (`python samples/_generate_utility_pdf.py`). The generator only writes a text-extractable PDF.

---

## 5. Travel JSON (3 min)

- [ ] **Imports → Travel** tab → open `samples/concur_reporting_v4_trip_response.json` in a text editor → copy the contents → paste into the textarea → Submit.
- [ ] Batch processes. **12 segments** across **3 trips**.
- [ ] The `LHR → XYZ` segment produces `UNRESOLVABLE_AIRPORT`.
- [ ] The SFO ↔ ORD return leg (null `distance_km`) shows a non-null `distance_km` after parse (filled by great-circle lookup).
- [ ] Segments split correctly by category:
    - AIR rows → `business_travel_air` (scope 3)
    - LODGING rows → `business_travel_lodging` (scope 3)
    - CAR rows → `business_travel_ground` (scope 3)

---

## 6. Queue filtering (2 min)

On the Queue page:

- [ ] Filter by **state = flagged** → only flagged rows visible.
- [ ] Filter by **source type = SAP** → only SAP rows.
- [ ] Filter by **source type = Travel** → only travel rows.
- [ ] Filter by **category = purchased_electricity** → only utility rows.
- [ ] Combine filters (e.g. flagged + SAP) → intersection only.
- [ ] Default sort is recent-first (by `activity_date`).
- [ ] Pagination works (if there are >25 rows visible).

---

## 7. Edit + approve flow (3 min)

- [ ] Open any row in the queue → detail view loads with all fields.
- [ ] Source-record section is visible and shows the raw payload as JSON.
- [ ] Edit `notes` → Save → 200 → version number increments by 1.
- [ ] Audit log section at the bottom shows the change with action `UPDATED`, a `request_id`, before/after values.
- [ ] Click **Approve** → state moves to `approved`. Audit log gets an `APPROVED` entry.
- [ ] For the `GAL` parse-error row (no ActivityRecord yet): edit the unit to `L`, save → record is now valid, anomaly hint may appear, state becomes `parsed` or `flagged`.

---

## 8. Optimistic locking (2 min)

- [ ] Open the same record in **two browser tabs** (Tab A and Tab B).
- [ ] In Tab A: edit `notes`, Save → 200 OK.
- [ ] In Tab B (still showing the old version): edit `notes` differently, Save → 412.
- [ ] A conflict dialog renders showing "Another analyst changed this — keep yours / take theirs / cancel."
- [ ] Choosing "take theirs" reloads with Tab A's value.
- [ ] Choosing "keep yours" overwrites and bumps the version again.

If the conflict dialog doesn't render, verify the frontend is reading the `version` field from responses and sending `If-Match` on PATCH.

---

## 9. Multi-tenancy (3 min)

- [ ] Note one record ID visible as `analyst@acme.test` (e.g. `#142`).
- [ ] Click the org dropdown in the header → switch to **Globex Industries**.
- [ ] Overview shows empty (no data uploaded to Globex yet) — or only Globex's seeded data.
- [ ] Queue page is empty for Globex.
- [ ] Imports page shows no Acme batches.
- [ ] In the browser address bar, navigate directly to `/queue/142` (the Acme record ID). Expected: 404 or "Not found", NOT a 200 leaking Acme data.
- [ ] Sign out, sign in as `analyst@globex.test` → same result. No Acme data visible.
- [ ] Sign out, sign back in as `analyst@acme.test` → all data returns.

This is the highest-stakes check in the test plan. If any Acme data is reachable as Globex (or vice versa), stop and fix before anything else.

---

## 10. Lock / Unlock (admin) (3 min)

- [ ] Sign out → sign in as `admin@acme.test`.
- [ ] Open an `approved` record → click **Lock**.
- [ ] A reason prompt appears (required field).
- [ ] Enter reason → confirm → state moves to `locked`. Audit log gets a `LOCKED` entry with the reason text.
- [ ] Sign out → sign in as `analyst@acme.test`.
- [ ] Open the locked record → edit fields are disabled / read-only. Attempting to PATCH via DevTools console returns 403.
- [ ] Sign back in as admin → click **Unlock** → reason required again → state returns to `approved`.
- [ ] Audit log shows `LOCKED` and `UNLOCKED` entries with both reasons.

---

## 11. Provenance trace (2 min)

- [ ] On any ActivityRecord detail view, locate the "Source" or "Batch" link.
- [ ] Click through to the source record → raw JSONB visible, line number matches the source file.
- [ ] Click through to the batch → file name, file hash (sha256), parser version, uploader, upload timestamp all visible.
- [ ] Going back from batch to a specific record works.

---

## 12. Anomaly hints (1 min)

Quick scan to confirm hints are surfaced:

- [ ] The 15,450 L SAP row → `ROLLING_MEDIAN_OUTLIER` with a reasoning string that includes the median value.
- [ ] The 1,075,000 kWh utility row → same code, similar reasoning shape.
- [ ] The `LHR → XYZ` travel segment → `UNRESOLVABLE_LOOKUP` or equivalent.

The reasoning strings should read like something an analyst would write (e.g. "value 1,075,000 kWh is 12× the 90-day rolling median of 89,500 kWh"). If they read like generic strings ("anomaly detected"), the explainability story breaks.

---

## 13. Error paths (2 min)

Things that should fail cleanly, not 500:

- [ ] Upload an empty CSV → 400 with a readable error.
- [ ] Upload a PNG renamed to `.csv` to the SAP tab → 400 with a readable error (not a 500 with a traceback).
- [ ] Paste invalid JSON to the Travel tab → 400 with a readable error.
- [ ] Upload a file > 50 MB (or whatever the limit is) → 413 or a friendly toast, not a silent failure.
- [ ] Submit a PATCH without `If-Match` header → 428 ("Precondition Required") or 412.
- [ ] Submit a PATCH with a non-numeric `If-Match` → 400.

If any of these returns a 500 with a traceback in the response, the error handling is leaking.

---

## 14. Session and CSRF (1 min)

- [ ] Sign in, then in DevTools delete the session cookie → next API call returns 401.
- [ ] CSRF token present in cookies after sign-in (`csrftoken`).
- [ ] All POST / PATCH / DELETE requests carry `X-CSRFToken` (visible in DevTools → Network).

---

## 15. Audit log integrity (1 min)

Open Django shell (`python manage.py shell`) and try:

```python
from core.models import AuditLog
log = AuditLog.objects.first()

# Should raise:
log.reason = "tampered"
log.save()

# Should also raise:
log.delete()

# Raw SQL should also fail:
from django.db import connection
with connection.cursor() as c:
    c.execute("UPDATE audit_log SET reason = 'tampered' WHERE id = %s", [log.id])
```

All three should raise an exception. The raw SQL UPDATE is the one that proves the DB trigger is in place; the others prove the model guards work.

---

## What "ready to deploy" looks like

All boxes ticked, plus:

- [ ] No 500s in the Django runserver output across the whole pass.
- [ ] No unhandled errors in the Celery worker terminal.
- [ ] No console errors in the browser DevTools (warnings are fine; errors are not).
- [ ] The four design docs read coherently top to bottom (`MODEL.md`, `DECISIONS.md`, `TRADEOFFS.md`, `SOURCES.md`).

If anything above failed, fix and re-run that section (you don't have to redo the whole pass — most sections are independent).

---

## Quick-reset cheat sheet

If state gets messy and you want to restart clean:

```bash
# Wipe Acme/Globex data, keep seed reference (units, factors, airports, plant codes, users)
python manage.py shell -c "
from ingestion.models import IngestionBatch
from emissions.models import ActivityRecord
from core.models import AuditLog
ActivityRecord.objects.all().delete()
IngestionBatch.objects.all().delete()
AuditLog.objects.all().delete()
"

# Or full reset (drops the DB):
psql -U postgres -c "DROP DATABASE breathe;"
psql -U postgres -c "CREATE DATABASE breathe OWNER breathe;"
python manage.py migrate
python manage.py seed_demo
```

The first option is usually enough between testing passes. The second is for when migrations or seed data themselves need to be re-verified.
