# Breathe ESG — emissions ingestion and analyst review

A Django REST + React prototype for the Breathe ESG tech intern assignment. The app ingests emissions data from three source types (SAP fuel and procurement, electricity usage from a utility portal, and corporate travel from Concur), normalizes everything against a versioned emission-factor catalog, and surfaces a review queue where an analyst can fix, approve, and lock rows for audit.

This README covers what's in the repo and how to run it. The reasoning behind the design lives in the four review docs listed below.

## Reading order for a reviewer

The grading rubric weights design judgment far above features, so the design docs are the substantive part of this submission.

1. [`MODEL.md`](MODEL.md) — the data model and the five requirements it has to satisfy (multi-tenancy, Scope 1/2/3, source-of-truth, units, audit trail).
2. [`DECISIONS.md`](DECISIONS.md) — every ambiguity in the brief, how it was resolved, and what would have gone back to the PM with more time.
3. [`TRADEOFFS.md`](TRADEOFFS.md) — three things deliberately left out of the build, each justified by something other than time pressure.
4. [`SOURCES.md`](SOURCES.md) — the per-source research (SAP, utility, Concur), why the sample data looks the way it does, and what would fail under real customer load.

For getting the app running, [`SETUP.md`](SETUP.md) is the full first-time walkthrough; [`DEPLOY.md`](DEPLOY.md) is the shorter Render-only runbook for when prerequisites are already installed.

## Repository layout

```
backend/         Django 5 + DRF + Celery
  breathe/       Project settings (split), middleware, Celery app
  core/          Organization, Membership, AuditLog, RLS migrations
  ingestion/     IngestionBatch, SourceRecord, ParseError, parsers, parse_batch task
  emissions/     ActivityRecord, EmissionFactor, CanonicalUnit, converters, review API
frontend/        Vite + React + TypeScript SPA (Tailwind + Radix)
samples/         Fabricated input files matching real-world source shapes
render.yaml      Blueprint: web + worker + Postgres + Redis + static site
```

## Architecture in one paragraph

Django REST API (gunicorn, two workers) backed by PostgreSQL with row-level security for tenant isolation and JSONB+GIN for raw source payloads. A Celery worker on a Redis broker handles parsing asynchronously so uploads of realistic file sizes don't block requests or hit Render's 30-second timeout. The React SPA on top uses session-cookie auth and optimistic locking on edits. The full diagram and the reasoning per component is in `MODEL.md`.

## Live demo

| | |
|---|---|
| App | _set after first Render deploy_ |
| Health | _`/healthz` on the web service_ |

Demo accounts (password `breathe` for all):

| Org | Email | Role |
|---|---|---|
| Acme Corp | `analyst@acme.test` | analyst |
| Acme Corp | `admin@acme.test` | admin |
| Globex Industries | `analyst@globex.test` | analyst |

The Globex account exists so a reviewer can verify multi-tenant isolation: sign in as Acme, switch to Globex from the header dropdown, confirm none of Acme's data is visible.

## End-to-end smoke test

The flow worth running first, signed in as `analyst@acme.test`:

1. **Imports → SAP** — drop `samples/sap_se16n_export_2026Q1.csv`. The batch moves `queued → parsing → complete` (the UI polls every two seconds). 48 rows, three deliberate errors: unmapped plant `ZZZZ`, unknown unit `GAL`, invalid date `33.03.2026`.
2. **Imports → Utility** — drop `samples/utility_portal_export_meter_xyz.csv`. 11 rows; the 1,075,000 kWh outlier produces an anomaly hint on the queue.
3. **Imports → Utility** — drop `samples/utility_bill_acme_facility_03_2026.pdf`. Generate it first with `python samples/_generate_utility_pdf.py`. One record extracted by pdfplumber.
4. **Imports → Travel** — paste the contents of `samples/concur_reporting_v4_trip_response.json`. 12 segments; the `LHR → XYZ` leg produces `UNRESOLVABLE_AIRPORT`.
5. **Imports → SAP** again with the same CSV. Response returns 200 with `deduped: true` (the `(organization, file_sha256)` uniqueness handles double-uploads and platform retries).
6. **Queue** — filter to `flagged`, open a row, correct the unit, **Save**. The audit log records the edit and tags it with the request ID.
7. Open the same record in two browser tabs, edit both, save the first → 200; save the second → 412 with a conflict banner.
8. Switch org to **Globex Industries** from the header. Confirm all Acme data disappears from every view.
9. Sign in as `admin@acme.test`, open an approved record, click **Lock**. Subsequent edit attempts return 403.

## Running locally

Prerequisites: Python 3.13, Node 20+, PostgreSQL 15+, Redis 7+ (or Memurai on Windows).

SQLite is not supported. Row-level security and JSONB indexes are core to the model, not optional optimizations — see `DECISIONS.md` #5.

```bash
# 1. Postgres
psql -U postgres -c "CREATE USER breathe WITH PASSWORD 'breathe' CREATEDB;"
psql -U postgres -c "CREATE DATABASE breathe OWNER breathe;"

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example ../.env      # then set DJANGO_SECRET_KEY

python manage.py migrate
python manage.py seed_demo
python manage.py runserver      # http://localhost:8000

# 3. Celery worker (separate shell, same venv)
celery -A breathe worker --loglevel=info    # add --pool=solo on Windows

# 4. Frontend (separate shell)
cd ../frontend
npm install
npm run dev                     # http://localhost:5173

# 5. Generate the utility PDF sample (one-time)
cd ../backend && python ../samples/_generate_utility_pdf.py
```

### Tests

The test suite is deliberately narrow. It targets the architectural claims rather than chasing coverage — see `DECISIONS.md` on why exhaustive tests were skipped at this scope.

```bash
cd backend

pytest core/tests/test_tenancy.py             # ORM-layer tenant isolation
pytest core/tests/test_rls.py                 # Postgres RLS enforcement
pytest core/tests/test_audit_immutable.py     # DB-trigger audit immutability
pytest emissions/tests/test_converters.py     # per-pair conversion + no cross-dimension entries
pytest emissions/tests/test_optimistic_locking.py
pytest ingestion/tests/                       # parser golden tests + parse_batch integration

pytest                                        # everything
```

## Deploying to Render

Full runbook in [`DEPLOY.md`](DEPLOY.md). The short version:

1. Push to GitHub. Share the private repo with `saurav@`, `rahul@`, and `shivang@breatheesg.com`.
2. Render → New → Blueprint → connect repo → Apply. `render.yaml` provisions web + worker + Postgres + Redis + the static frontend.
3. Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CORS_ALLOWED_ORIGINS` on the web service. Set `VITE_API_BASE_URL` on the frontend, then trigger a manual redeploy so the value lands in the JS bundle.
4. Open the web service shell and run `python manage.py seed_demo`.
5. Run the smoke test above against the live URLs.

## A note on what's here

The intent was to submit a smaller app with a defensible data model, not a feature-complete platform. The four design docs explain every non-obvious choice — including the ones that look like gaps. Anything that looks missing should be cross-referenced against `TRADEOFFS.md` and `DECISIONS.md` before being treated as an omission.
