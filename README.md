# Somali Fish Traceability

Somali Fish Traceability is a FastAPI application for recording fish from
landing through processing and export. It provides role-protected vessel
management, lot lineage and recall operations, public lot trace reports, and
PDF traceability certificates. This traceability helps seafood businesses and
authorities identify a product's source and downstream destinations.

## Tech stack

- Python 3.10+
- FastAPI and Jinja2 templates
- PostgreSQL on Supabase
- SQLAlchemy
- Pytest and FastAPI `TestClient`

## Setup

### 1. Install

From the project root, create and activate a virtual environment, then install
the backend dependencies:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### 2. Configure PostgreSQL/Supabase

Create a Supabase project and obtain its PostgreSQL connection string from
**Project Settings → Database**. The project API URL is
`https://utdegtyzzisvkxadlbhx.supabase.co`; it is not itself the PostgreSQL
connection string. Copy `.env.example` to `backend/.env`, then set `DATABASE_URL`
to the connection string (including `sslmode=require`) and replace `JWT_SECRET`
with a long random secret. The app also accepts the existing variable names
`JWT_SECRET_KEY` and `JWT_ALGORITHM`; those take precedence over `JWT_SECRET`
and `ALGORITHM` if both are set.

Run the SQL files in `backend/migrations/` in numeric order using the Supabase
SQL Editor or a PostgreSQL client. `002_seed.sql` creates demo-only users and
sample records. Never use its shared demo password in a production environment.
For an existing database, apply the new numbered migrations before restarting
the app; `005_processing_export_audit.sql` adds inspection timestamps and the
audit log, and `006_temperature_type.sql` adds chilled/frozen temperature
classification. `007_mock_payments.sql` adds persistence for simulated mobile
money payment receipts.

### 3. Run the application

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir backend --reload
```

The API is available at <http://127.0.0.1:8000>; interactive API docs are at
<http://127.0.0.1:8000/docs>.

## Demo accounts

These accounts are added only when you apply `backend/migrations/002_seed.sql`.
All currently use the seed-only password `ChangeMe-Seed-Only-2026!`.

| Role | Email |
|---|---|
| Admin | `admin@example.test` |
| Officer | `officer.berbera@example.test` |
| Officer | `officer.bosaso@example.test` |
| Processor | `processor@example.test` |
| Inspector | `inspector@example.test` |
| Exporter | `exporter@example.test` |

These are local/demo credentials, not production accounts. Change or remove
them before deploying.

## Mock mobile payments and SMS

The authenticated `/payments` page simulates payments through **EVC Plus** and
**Zaad**. It accepts a phone number and a positive amount in USD, stores a
receipt in `payment_transactions`, and queues a confirmation message in the
existing `sms_outbox` table. The authenticated `/sms-outbox` page lists queued
messages; Admins have sidebar links to both pages.

These are demo adapters only: they do not contact mobile-money or SMS
providers and do not transfer money or deliver text messages. Apply
`backend/migrations/007_mock_payments.sql` after migrations 001–006 before
using payments with an existing database.

## Seeding pitch/demo data

After applying migrations 001–007 and creating the demo users with
`002_seed.sql`, verify that `backend/.env` points to a demo/development
database, then run this from the repository root:

```powershell
python backend\seed_demo_data.py --confirm
```

The script adds the showcase catch-to-export workflow, mock payment receipts,
and SMS outbox entries in one transaction. It does not delete existing data,
and a complete showcase dataset is detected on subsequent runs. The `--confirm`
flag is required as a safeguard against accidentally seeding a production
database.

## Tests

Install dependencies as above, then run all 15 backend pytest modules from the
project root:

```powershell
$env:PYTHONPATH = "$PWD\backend"
$env:DATABASE_URL = "postgresql://postgres:ci-placeholder@localhost:5432/fish_traceability"
$env:JWT_SECRET_KEY = "test-only-secret"
python -m pytest -q
```

The tests use FastAPI `TestClient` and isolated/mocked persistence; they do not
need a live Supabase project or database.

## Assumptions made: ...

- The existing backend and SQL migrations define the intended routes, schemas,
  role names, and demo users.
- Local application configuration is loaded from `backend/.env`, so copy the
  root example there rather than placing secrets in source control.
- CI validates backend behavior without a live PostgreSQL database; the
  configured database URL is only used to initialize the SQLAlchemy engine.
- No separate frontend test suite is present, so CI runs pytest only.
