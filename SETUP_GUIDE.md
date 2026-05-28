# Breathe ESG - Complete Setup Guide for Windows

## Prerequisites Check
- ✅ Python 3.10+ (you have 3.10.2)
- ✅ Node.js 20+ (you have v22.20.0)
- ❌ PostgreSQL 15+ (NOT installed yet) - **REQUIRED**
- ❌ Redis 7+ (optional for demo, required for production)

---

## Step 1: Install PostgreSQL (CRITICAL - Do This First)

### Step 1.1: Download PostgreSQL
1. Go to: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
2. Click **PostgreSQL 15** → **Windows x86-64** → Download

### Step 1.2: Run the Installer
1. Double-click the downloaded file (`postgresql-15-x64-installer.exe`)
2. Click "Next" through the wizard
3. **Important settings:**
   - **Installation Directory**: Leave default (C:\Program Files\PostgreSQL\15)
   - **Port**: Keep as `5432` (default)
   - **Superuser**: Keep as `postgres`
   - **Password**: Type `postgres` (or remember your password!)
   - **Port**: `5432`
   - **Locale**: Default
4. Click "Next" → "Install" → Wait 2-5 minutes
5. Click "Finish" (uncheck "Launch Stack Builder" if offered)

### Step 1.3: Verify PostgreSQL is Running
Open **PowerShell** and run:
```powershell
psql -U postgres -c "SELECT version();"
```

If you see a version number, PostgreSQL is running! ✅

If it asks for a password, type the password you set during installation.

---

## Step 2: Create the Database and User

Open **PowerShell** and run:
```powershell
psql -U postgres
```

You'll see a prompt like: `postgres=#`

Now paste these commands one-by-one:
```sql
CREATE USER breathe WITH PASSWORD 'breathe' CREATEDB;
CREATE DATABASE breathe OWNER breathe;
\q
```

**What it does:**
- Creates a user `breathe` with password `breathe`
- Creates a database `breathe` owned by that user
- `\q` exits psql

---

## Step 3: Verify Database Setup

Run this to confirm:
```powershell
psql -U breathe -d breathe -c "SELECT 'Connected to breathe database!' as status;"
```

You'll be prompted for password: type `breathe`

You should see:
```
            status
──────────────────────
Connected to breathe database!
```

✅ If you see this, your database is ready!

---

## Step 4: Backend Setup

### Step 4.1: Navigate to Backend
```powershell
cd C:\Users\sheet\Downloads\Breathe\backend
```

### Step 4.2: Activate Python Virtual Environment
```powershell
.\.venv\Scripts\activate
```

You should see `(.venv)` at the start of your prompt.

### Step 4.3: Run Django Migrations
This creates all the database tables:
```powershell
python manage.py migrate
```

You should see:
```
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, sessions, core, ingestion, emissions
Running migrations:
  Applying core.0001_initial... OK
  Applying core.0002_rls_policies... OK
  ...
```

### Step 4.4: Seed Demo Data
Load the demo accounts and sample data:
```powershell
python manage.py seed_demo
```

You should see:
```
Created organization: Acme Corp
Created organization: Globex Industries
Created users for demo accounts
```

### Step 4.5: Start Django Server
```powershell
python manage.py runserver 0.0.0.0:8000
```

You should see:
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
Django version 5.1.4
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

✅ **Leave this terminal open and running!**

---

## Step 5: Frontend Setup

### Step 5.1: Open a NEW PowerShell Window
Press `Win + Shift + 2` or open a new PowerShell window

### Step 5.2: Navigate to Frontend
```powershell
cd C:\Users\sheet\Downloads\Breathe\frontend
```

### Step 5.3: Start Frontend Dev Server
```powershell
npm run dev
```

You should see:
```
> breathe-frontend@0.1.0 dev
> vite

  VITE v6.4.2  ready in 1976 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

✅ **Leave this terminal open and running!**

---

## Step 6: Access the Application

### Step 6.1: Open Browser
1. Go to: **http://localhost:5173/**

### Step 6.2: Demo Login
You should see the login page with demo accounts. Click one of these buttons:

| Org | Email | Password |
|---|---|---|
| Acme (analyst) | analyst@acme.test | breathe |
| Acme (admin) | admin@acme.test | breathe |
| Globex (analyst) | analyst@globex.test | breathe |

Or enter credentials manually.

### Step 6.3: You're In!
Once logged in, you should see:
- **Imports** tab - upload sample CSV files
- **Queue** tab - review & approve emissions records
- **Overview** tab - dashboard
- **Settings** tab - organization settings

---

## Step 7: Optional - Celery Worker (for async tasks)

If you want to process file imports asynchronously (optional):

### Step 7.1: Install Redis (OPTIONAL)
For production/advanced use. For now, skip this.

### Step 7.2: Open a THIRD PowerShell Window
```powershell
cd C:\Users\sheet\Downloads\Breathe\backend
.\.venv\Scripts\activate
celery -A breathe worker --loglevel=info
```

This starts the background task worker.

---

## Summary: What Should Be Running

You should have **2-3 terminals open**:

| Terminal | Command | Status |
|----------|---------|--------|
| Terminal 1 | `python manage.py runserver` | Running on http://localhost:8000 |
| Terminal 2 | `npm run dev` | Running on http://localhost:5173 |
| Terminal 3 (optional) | `celery -A breathe worker` | Running background tasks |

---

## Testing: End-to-End Flow

After logging in as `analyst@acme.test`:

1. **Imports** → **SAP** tab → drop `samples/sap_se16n_export_2026Q1.csv`
   - Should process: `queued → parsing → complete`
2. **Queue** → see the uploaded records
3. **Overview** → see dashboard with emissions data

---

## Troubleshooting

### Error: "psql: command not found"
**Solution:** PostgreSQL wasn't installed or PATH not updated
- Reinstall PostgreSQL
- Or add to PATH: `C:\Program Files\PostgreSQL\15\bin`

### Error: "connection refused" on localhost:8000
**Solution:** Django server not running
- Check Terminal 1 is still showing Django server
- If crashed, see error message and share it

### Error: "Cannot GET /" on localhost:5173
**Solution:** Frontend dev server not running
- Check Terminal 2 is still showing Vite server
- Run: `npm run dev` in frontend folder

### Database: "role 'breathe' does not exist"
**Solution:** User wasn't created in Step 2
- Re-run Step 2 to create the user

### Error: "Module not found: django"
**Solution:** Virtual environment not activated
- Run: `.\.venv\Scripts\activate`
- Should see `(.venv)` in prompt

---

## Next Steps

After setup works:
1. Read `MODEL.md` - understand the data model
2. Read `DECISIONS.md` - architecture decisions
3. Explore the UI and try uploading sample files
4. Review `SOURCES.md` for production considerations

---

## Quick Commands Reference

```powershell
# Backend
cd C:\Users\sheet\Downloads\Breathe\backend
.\.venv\Scripts\activate
python manage.py runserver 0.0.0.0:8000
python manage.py migrate
python manage.py seed_demo

# Frontend
cd C:\Users\sheet\Downloads\Breathe\frontend
npm run dev

# Database
psql -U breathe -d breathe
```

---

**You're all set! 🎉**
