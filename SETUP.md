# Setup

End-to-end walkthrough, from no tools installed to a deployed submission. Roughly 60–90 minutes the first time; subsequent deploys are under 10.

Commands below use bash / zsh (macOS, Linux, WSL). Windows PowerShell users: replace `source .venv/bin/activate` with `.venv\Scripts\Activate.ps1`. Where relevant, Windows-specific notes are inline.

## 1. Prerequisites

Five tools are needed. Install in this order and open a fresh terminal after each so PATH updates take effect.

| Tool | Version | Source | Verify |
|---|---|---|---|
| Python | 3.13.x | <https://www.python.org/downloads/> | `python --version` |
| Node.js | 20 or higher | <https://nodejs.org/> (LTS) | `node --version` |
| Git | any recent | <https://git-scm.com/downloads> | `git --version` |
| PostgreSQL | 15 or higher | <https://www.postgresql.org/download/> | `psql --version` |
| Redis | 7 or higher | macOS: `brew install redis`. Windows: Memurai (<https://www.memurai.com>) or Docker. Linux: distro package. | `redis-cli ping` returns `PONG` |

A note on Windows + Celery: the default prefork worker pool doesn't work there. Celery is started with `--pool=solo` further down; that flag is already included for the Windows path.

## 2. Database

Connect as the Postgres superuser (`psql -U postgres -h localhost` — it'll prompt for the password set during install) and run:

```sql
CREATE USER breathe WITH PASSWORD 'breathe' SUPERUSER CREATEDB;
CREATE DATABASE breathe OWNER breathe;
\q
```

Verify:

```bash
psql -U breathe -h localhost -d breathe -c "SELECT current_user, current_database();"
```

Expected output: `breathe | breathe`.

A note on `SUPERUSER` for the local dev user: Postgres RLS policies still apply to the table owner under `FORCE ROW LEVEL SECURITY`, but superusers always bypass them. Locally, the convenience of `seed_demo` "just working" outweighs the RLS-enforcement signal — the dedicated RLS tests in `core/tests/test_rls.py` explicitly switch to a non-superuser role to prove the policies hold. In production on Render, the app role should not be a superuser. That part is covered in `DEPLOY.md`.

## 3. Redis

macOS, started via Homebrew:

```bash
brew services start redis
redis-cli ping        # PONG
```

Windows with Memurai: it installs as a service. Start it from `services.msc` if not already running, then `memurai-cli ping`.

Docker route on any platform:

```bash
docker run -d --name breathe-redis -p 6379:6379 redis:7-alpine
```

## 4. Backend

From the repo root, into the backend directory:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
```

The prompt should now show `(.venv)`. If PowerShell blocks the activate script with an execution-policy error, run this once and try again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This pulls Django 5.1, DRF, Celery, structlog, pdfplumber, psycopg, and a few others. Two minutes or so.

Configure environment variables from the repo root:

```bash
cd ..
cp .env.example .env
```

Open `.env` and set:

```
DJANGO_SECRET_KEY=<paste any 50-character random string>
```

A reasonable way to generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

The defaults for `DATABASE_URL` (`postgres://breathe:breathe@localhost:5432/breathe`) and `REDIS_URL` (`redis://localhost:6379/0`) match the local setup above. No other edits are needed for local dev.

Back in `backend/` with the venv still active:

```bash
python manage.py migrate
python manage.py seed_demo
```

`seed_demo` is idempotent. It creates seven canonical units, eight emission categories, ten emission factors, thirty airports, two organizations (Acme Corp and Globex Industries), six plant codes, and three demo users (all with the password `breathe`).

One-time: generate the sample utility PDF. The repo ships the generator, not the binary.

```bash
python ../samples/_generate_utility_pdf.py
```

Commit the resulting `samples/utility_bill_acme_facility_03_2026.pdf` before pushing.

## 5. Run the backend (two terminals)

Keep two backend terminals open from here on.

**Terminal A — API:**

```bash
cd backend
source .venv/bin/activate
python manage.py runserver
```

Sanity check from a third shell:

```bash
curl http://127.0.0.1:8000/healthz
# {"status": "ok"}
```

**Terminal B — Celery worker:**

```bash
cd backend
source .venv/bin/activate
celery -A breathe worker --loglevel=info
# Windows: add --pool=solo
```

Output ends with `celery@<hostname> ready.`.

## 6. Frontend

**Terminal C — frontend:**

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## 7. Local smoke test

This is the same flow a reviewer will run on the live URL. Running it locally first catches problems before they become Render problems.

Signed in as `analyst@acme.test` (clicking the row on the login page prefills the form):

1. **Imports → SAP** — drop `samples/sap_se16n_export_2026Q1.csv`. The batch moves `queued → parsing → complete`. Expect 48 rows and three errors: `UNMAPPED_PLANT`, `UNKNOWN_UNIT`, `BAD_DATE`.
2. **Imports → Utility** — drop the CSV, then the PDF. 11 + 1 records.
3. **Imports → Travel** — paste the contents of `samples/concur_reporting_v4_trip_response.json`. 12 segments, one unresolvable airport.
4. Re-drop the SAP file. Response shows `Already imported — batch #N` (the file_sha256 idempotency check is working).
5. **Queue** → filter `flagged` → open any row → fix the unit on the `GAL` row (change to `L`), or just **Approve** any other row. The status chip should update.
6. Open the same record in two browser tabs, edit the `notes` field in each, save the first → 200. Save the second → "Conflict — another analyst edited this record."
7. Header dropdown → switch to **Globex Industries** → confirm none of Acme's data is visible on Overview, Queue, or Imports.

If all seven pass, the app is end-to-end working locally.

### Optional: run the tests

```bash
cd backend
source .venv/bin/activate
pytest
```

The narrow tests that prove the architectural claims:

```bash
pytest core/tests/test_rls.py
pytest core/tests/test_audit_immutable.py
pytest emissions/tests/test_converters.py
pytest emissions/tests/test_optimistic_locking.py
pytest ingestion/tests/
```

## 8. Push to GitHub

From the repo root, with local working:

```bash
git init
git add -A
git status            # double-check no secrets are about to be committed
git commit -m "Initial commit: Breathe ESG prototype"
git branch -M main
```

Create the repo on GitHub (private is fine — the brief says so), without initializing it with a README, .gitignore, or license. Then:

```bash
git remote add origin https://github.com/<username>/<repo-name>.git
git push -u origin main
```

Share the repo (Settings → Collaborators) with:

- `saurav@breatheesg.com`
- `rahul@breatheesg.com`
- `shivang@breatheesg.com`

## 9. Deploy to Render

### 9a. Connect the Blueprint

1. Sign in at <https://render.com>.
2. **New** → **Blueprint**.
3. Connect the GitHub account, pick the repo.
4. Render reads `render.yaml` and shows five resources: `breathe-postgres`, `breathe-redis`, `breathe-web`, `breathe-worker`, `breathe-frontend`.
5. Apply.

First build is about five minutes for the backend (pip install + collectstatic + migrate) and about three for the frontend (npm ci + vite build).

### 9b. Environment variables

Any variable marked `sync: false` in `render.yaml` will prompt in the dashboard. Set these on **breathe-web** — values are case-sensitive:

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | click **Generate Value** | Render generates a 50-char random string |
| `DJANGO_ALLOWED_HOSTS` | the actual web service hostname (e.g. `breathe-web.onrender.com`) | No `https://`, no trailing slash |
| `DJANGO_CORS_ALLOWED_ORIGINS` | the actual frontend URL with `https://`, no trailing slash | Has to match exactly |
| `SENTRY_DSN` | optional | App runs fine without it |

On **breathe-frontend**:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | the actual backend URL with `https://` |

After setting `VITE_API_BASE_URL`, trigger a manual redeploy on the frontend — the value gets baked into the JS bundle at build time.

### 9c. Seed production data

In the Render dashboard, open the **breathe-web** service → **Shell**:

```bash
python manage.py seed_demo
```

Optional: a Django superuser for `/admin/` debugging.

```bash
python manage.py createsuperuser
```

(Demo users aren't staff. Skip if `/admin/` isn't needed.)

## 10. Verify production

### 10a. Process up

```bash
curl https://<web-host>/healthz
# {"status": "ok"}
```

### 10b. Database and Redis reachable

```bash
curl https://<web-host>/readyz
# {"db": true, "redis": true}
```

If either is false, check the corresponding service's logs in Render.

### 10c. Frontend loads

Open the frontend URL in a browser. The sign-in page should appear with the three demo accounts listed inline.

### 10d. Smoke test on the live URL

Same seven steps as in section 7, against the deployed URLs. If step 1 (login) returns 403:

- Verify `DJANGO_CORS_ALLOWED_ORIGINS` exactly matches the frontend URL (no trailing slash, `https://`, no typos).
- Verify `VITE_API_BASE_URL` matches the backend URL and that the frontend was redeployed after the variable was set.

If step 2 (upload) returns 202 but the batch stays `queued`:

- Check the breathe-worker logs in Render. Usually it can't reach Redis — verify `REDIS_URL` is set on the worker.

## 11. Submitting

Reply to the assignment email with the GitHub URL, the live URL, and the three demo accounts (password `breathe`). The four design docs in suggested reading order: `MODEL.md`, `DECISIONS.md`, `TRADEOFFS.md`, `SOURCES.md`. The README's reading-order section already lists this.

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| `psql: connection refused` | Postgres service not running | macOS: `brew services start postgresql`. Windows: `services.msc` → PostgreSQL → Start. |
| `permission denied for schema public` during migrate | The `breathe` user isn't owner of the DB | Re-run `CREATE DATABASE breathe OWNER breathe;` |
| `seed_demo` error: "new row violates row-level security policy" | The `breathe` user isn't `SUPERUSER` | `ALTER USER breathe WITH SUPERUSER;` from the `postgres` prompt |
| Celery worker reports `Connection refused` for Redis | Redis not running, or wrong port | `redis-cli ping` |
| Celery worker won't start on Windows | Default prefork pool incompatible | Add `--pool=solo` (already in section 5) |
| Sign-in fails with 403 in the network tab | CSRF or CORS misconfiguration | Check that `DJANGO_CORS_ALLOWED_ORIGINS` matches the frontend origin exactly |
| Sign-in fails with 401 | Wrong password or seed didn't run | Re-run `seed_demo`; the password is `breathe` |
| Upload returns 202 but the batch stays `queued` forever | Worker not running, or can't reach Redis | Check worker logs |
| 502 Bad Gateway on first Render request | Free-tier cold start (~30–50s) | Wait and retry |
| Render Postgres "suspended" after 90 days | Free Postgres expires after 90 days | Pay for Render's starter Postgres ($7/mo), or point `DATABASE_URL` at Neon's free tier |
| pdfplumber error during PDF upload | The PDF isn't text-extractable | Re-generate with `_generate_utility_pdf.py` |

For Render-specific reference details (env-var reference, rollback, log locations), see `DEPLOY.md`.
