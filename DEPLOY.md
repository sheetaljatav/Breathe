# Deploy

Render-specific runbook. For full first-time setup (installing prerequisites, running locally), see `SETUP.md`. This document assumes the app already runs locally.

About 20 minutes the first deploy, five minutes for subsequent ones.

## Prerequisites

- The repo pushed to GitHub (private or public — both work).
- A Render account. Free tier is enough for the prototype: free Postgres for 90 days, free Redis at 25 MB, free web and worker dynos with cold-start latency.

## 1. Push to GitHub

```bash
git init                # only on the first push
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<username>/<repo-name>.git
git push -u origin main
```

Share the private repo (Settings → Collaborators) with:

- `saurav@breatheesg.com`
- `rahul@breatheesg.com`
- `shivang@breatheesg.com`

## 2. Apply the Blueprint

In the Render dashboard:

1. **New** → **Blueprint**.
2. Connect the GitHub repo.
3. Render reads `render.yaml` and shows five resources:
   - `breathe-postgres` (Postgres database)
   - `breathe-redis` (Redis service)
   - `breathe-web` (Django web service)
   - `breathe-worker` (Celery worker)
   - `breathe-frontend` (static site)
4. Apply.

First build is around five minutes for the backend (`pip install` + `collectstatic` + `migrate`) and three minutes for the frontend (`npm ci` + `vite build`).

## 3. Environment variables

Anything marked `sync: false` in `render.yaml` will prompt in the dashboard. Values below are case-sensitive — exact strings only.

On **breathe-web**:

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | click **Generate Value** | Render generates a 50-char random string |
| `DJANGO_ALLOWED_HOSTS` | the actual web service hostname | No `https://`, no trailing slash |
| `DJANGO_CORS_ALLOWED_ORIGINS` | the actual frontend URL with `https://`, no trailing slash | Has to match exactly |
| `SENTRY_DSN` | optional | App runs fine without it |

On **breathe-frontend**:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | the backend URL with `https://` |

After setting `VITE_API_BASE_URL`, click **Manual Deploy → Deploy latest commit** on the frontend. The variable is baked into the JS bundle at build time, so an existing build won't see it.

## 4. Seed production data

The web service has no users or reference data until seed runs. Render dashboard → breathe-web → **Shell**:

```bash
python manage.py seed_demo
```

This creates:

- 7 canonical units, 8 emission categories, 10 cited emission factors, 30 airports.
- 2 orgs (Acme Corp, Globex Industries).
- 3 demo users (`analyst@acme.test`, `admin@acme.test`, `analyst@globex.test`; password `breathe`).

The command is idempotent.

Optionally create a Django superuser for the `/admin/` interface — useful for ops debugging, not required for the demo flow:

```bash
python manage.py createsuperuser
```

## 5. Generate the utility PDF sample

The repo doesn't ship the PDF (binary); it ships the generator. Run once locally and commit the output:

```bash
cd backend
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python ../samples/_generate_utility_pdf.py
git add ../samples/utility_bill_acme_facility_03_2026.pdf
git commit -m "samples: add generated utility PDF"
git push
```

Render redeploys automatically on push.

## 6. Verify

Each check should pass before moving to the next.

**6a. Process up:**

```bash
curl https://<web-host>/healthz
# {"status": "ok"}
```

**6b. Database and Redis reachable:**

```bash
curl https://<web-host>/readyz
# {"db": true, "redis": true}
```

If `db` is false, check the Render Postgres status. If `redis` is false, check the Redis service.

**6c. Frontend loads.** Open the frontend URL. The sign-in page should render with the three demo accounts visible inline.

**6d. Login works.** Click a demo account row to prefill, then **Sign in**. The Overview page should load.

If login returns 403, the cause is usually one of:

- `DJANGO_CORS_ALLOWED_ORIGINS` doesn't exactly match the frontend URL.
- `VITE_API_BASE_URL` doesn't match the backend URL — and the frontend wasn't redeployed after the variable was set.
- `SESSION_COOKIE_SAMESITE` isn't `None` in production settings (verify `backend/breathe/settings/prod.py`).

**6e. Sentry receiving events (only if `SENTRY_DSN` is set):**

```bash
python manage.py shell -c "raise RuntimeError('sentry-deploy-verify')"
```

Or visit `/api/_internal/sentry-test` as a signed-in superuser. The event should appear in Sentry within about 30 seconds.

## 7. End-to-end smoke test

Signed in as `analyst@acme.test`:

1. **Imports → SAP** — drop `samples/sap_se16n_export_2026Q1.csv`. Status: `queued → parsing → complete`. 48 rows, three errors: `UNMAPPED_PLANT`, `UNKNOWN_UNIT`, `BAD_DATE`.
2. **Imports → Utility** — drop the CSV, then the PDF. 11 + 1 records.
3. **Imports → Travel** — paste the contents of `samples/concur_reporting_v4_trip_response.json`. 12 segments, one unresolvable airport.
4. Re-drop the SAP file → `deduped: true`. Same `file_sha256`, no new batch.
5. **Queue** → filter `flagged` → open a row → fix the unit → **Approve**.
6. Open the same record in two browser tabs, edit each, save the first → 200; save the second → conflict banner.
7. Header dropdown → switch to **Globex Industries** → confirm none of Acme's data is visible.
8. Sign in as `admin@acme.test`, navigate to an approved record, click **Lock**. As `analyst@acme.test`, confirm further edits return 403.

All eight passing means the deploy is good.

## 8. Submission email

Reply to the assignment email with the GitHub URL, the live URL, the three demo accounts, and a note about which docs to read in which order. The README has the reading-order section already.

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| 502 Bad Gateway on first request | Free-tier dyno cold start | Wait 30–50s; subsequent requests are fast |
| Login form returns 403 | `DJANGO_CORS_ALLOWED_ORIGINS` doesn't match the frontend URL | Fix the env var on breathe-web; redeploy |
| Login succeeds, every subsequent request returns 401 | Session cookie blocked cross-origin | Verify `SESSION_COOKIE_SAMESITE = "None"` and `SESSION_COOKIE_SECURE = True` in `prod.py` |
| Upload returns 202, batch stays `queued` forever | Worker not running, or can't reach Redis | Check breathe-worker logs; verify `REDIS_URL` is set on the worker |
| `/api/batches/` returns 500 with "no migrations" | Migrations didn't run during build | Render shell: `python manage.py migrate` |
| Render Postgres "free tier suspended" after 90 days | Free Postgres expires at 90 days | Pay for Render's $7/mo starter, or point `DATABASE_URL` at Neon or Supabase free tier (both support RLS and JSONB+GIN) |

## Reverting a bad deploy

Render keeps deployment history. Dashboard → breathe-web → **Deploys** → click the previous green deploy → **Rollback to this deploy**. Same for the frontend.

If a migration is what broke things, the schema needs to be rolled back too:

```bash
python manage.py migrate <app> <previous_migration>
```

run in the Render shell before rolling back the code, otherwise the old code will hit the new schema.
