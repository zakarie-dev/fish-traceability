# Somali Fish Traceability

Somali Fish Traceability addresses a market problem: without reliable catch-origin and cold-chain records, Somali exporters struggle to prove product quality to premium buyers, and a bad batch is difficult to trace. The system records fish from catch and landing through processing, cold-chain handling, inspection, and export, then traces lots through splits and merges back to source catches and forward to affected consignments during a recall.

## Feature status

| Feature | Status | Current implementation |
|---|---|---|
| Login and roles | Implemented | JWT login, bcrypt password hashes, server-side role checks, and demo users for five roles. |
| Vessel and landing-site registry | Partial | Admin pages and create forms exist; full edit/inactive-site management and every licence rule need verification. |
| Catch and lot recording | Partial | Officer form creates a catch and its first lot, with positive weight/date validation; protected-species, expired-licence, and assigned-site rules are not fully enforced. |
| Lot genealogy | Implemented | Split/merge links, backward trace, forward recall, and split weight/loss validation. |
| QR lot labels | Partial | Printable lot label and QR image route exist; reprint logging is not implemented. |
| Processing | Partial | Processing steps and yield are recorded; verify that each workflow updates current lot weight as required. |
| Cold chain | Partial | Chilled/frozen readings and temperature threshold breaches are recorded; six-hour gap alerts and a plotted temperature history remain to be verified/finished. |
| Inspections | Partial | Inspector records pass/fail and grade; freshness checklist, photo capture, and full post-breach review workflow are limited. |
| Export consignments | Partial | Eligible lots can be assigned at creation; shipping lock and full edit/remove workflow are limited. |
| Export certificates | Partial | PDF and trace QR are generated; confirm all required issuance gates and PDF fields before treating as authority-ready. |
| Public traceability | Implemented | Public lot trace includes lineage and downstream consignment data without owner phone numbers or prices. |
| Dashboard | Implemented | Database-backed inventory/export metrics and species/site charts. |
| English and Somali | Partial | Language switch and translations exist; review every page and generated document for complete Somali coverage. |
| Simulated payments and SMS | Partial | EVC Plus/Zaad mock payments, receipts, and SMS outbox; no real provider is contacted and eDahab is not implemented. |

“Implemented” describes a code path present in this repository; it does not mean every business edge case has passed live-system testing. See [Known limitations](#known-limitations) and the [API/module reference](docs/API_AND_MODULE_REFERENCE.md).

## Screenshots

Screenshots below show the local demo application and sample data. The dashboard home-page screenshot is the image supplied for this project.

| Screen | Preview |
|---|---|
| Dashboard home page | ![Fish Traceability dashboard home page](docs/screenshots/dashboard-home.png) |
| Login | ![Login page](docs/screenshots/login.png) |
| Lots | ![Lot inventory](docs/screenshots/lots.png) |
| Lot detail | ![Lot detail](docs/screenshots/lot-detail.png) |
| Landing sites | ![Landing sites](docs/screenshots/landing-sites.png) |
| Consignments | ![Consignments](docs/screenshots/consignments.png) |
| Public trace | ![Public trace search](docs/screenshots/trace.png) |

## Architecture

```mermaid
flowchart LR
    Browser[Browser and Jinja templates] --> Routes[FastAPI page/API routes]
    Routes --> Services[Business services]
    Services --> Repositories[SQLAlchemy repositories]
    Repositories --> PostgreSQL[(Supabase PostgreSQL)]
    Routes --> Adapters[Mock payment and SMS adapters]
    Adapters --> PostgreSQL
```

The browser is rendered with Jinja2 templates. FastAPI routes handle HTTP forms/API requests and authentication; services enforce transactional business rules; repositories perform reusable persistence queries; PostgreSQL stores the relational records. See the [API and module reference](docs/API_AND_MODULE_REFERENCE.md) and [database relationships](docs/DATABASE.md).

## Technology

| Component | Version / detail |
|---|---|
| Python | 3.12.0 used for the current local verification; project setup targets Python 3.10+ |
| FastAPI | 0.162.0 in the current local environment |
| Jinja2 | 3.1.6 |
| Uvicorn | 0.54.0 |
| SQLAlchemy | 2.1.8 |
| PostgreSQL | Supabase PostgreSQL |
| Pydantic | 2.14.2 |
| Pytest | 9.2.0 |

These are versions observed in the review environment, not a lockfile: [`backend/requirements.txt`](backend/requirements.txt) currently does not pin dependency versions.

## Setup from a fresh Windows computer

### 1. Install Python and dependencies

Install Python 3.10 or later, then run in PowerShell from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### 2. Configure PostgreSQL

Create/use a development Supabase PostgreSQL database. Copy the checked-in sample environment file and edit the copy:

```powershell
Copy-Item .env.example backend\.env
```

Set `DATABASE_URL` to the PostgreSQL connection string from Supabase **Project Settings → Database** (not the Supabase API URL), including `sslmode=require`. Replace the JWT secret with a long random value. Never commit `backend/.env`; keep the checked-in `.env.example` templates as placeholders only.

Settings:

| Name | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL/Supabase connection string |
| `JWT_SECRET` or `JWT_SECRET_KEY` | JWT signing secret; the `JWT_SECRET_KEY` name takes precedence |
| `ALGORITHM` or `JWT_ALGORITHM` | JWT algorithm; the `JWT_ALGORITHM` name takes precedence |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Login token lifetime |
| `PUBLIC_TRACE_BASE_URL` | Base URL encoded in printed QR labels and certificates |

### 3. Create schema and demo accounts

In the Supabase SQL Editor (or a PostgreSQL client), apply the scripts in `backend/migrations/` in numeric order, **001 through 007**. `002_seed.sql` creates the demo users and Somali sample locations/species/vessels as part of this sequence. The later migrations add lot workflow support, audit records, temperature type, and mock payment receipts. On an existing database, apply only migrations that have not already run.

To add the showcase catch-to-export dataset, first verify `backend/.env` targets a demo/development database. Then run:

```powershell
python backend\seed_demo_data.py --confirm
```

This script is additive and refuses to seed without `--confirm`; do not point it at production data.

### 4. Start and open the application

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

- Web app: <http://127.0.0.1:8000/login>
- OpenAPI/Swagger: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

The root path is not a landing page; use `/login` or `/dashboard`.

## Demo accounts

Apply `002_seed.sql` to create these accounts. All use the demo-only password `ChangeMe-Seed-Only-2026!`.

| Role | Email |
|---|---|
| Admin | `admin@example.test` |
| Officer (Berbera) | `officer.berbera@example.test` |
| Officer (Bosaso) | `officer.bosaso@example.test` |
| Processor | `processor@example.test` |
| Inspector | `inspector@example.test` |
| Exporter | `exporter@example.test` |

These shared credentials are for a local demo only. Never deploy them or use them for real accounts.

## Running tests

From the project root, activate the virtual environment and run:

```powershell
$env:PYTHONPATH = "$PWD\backend"
$env:DATABASE_URL = "postgresql://test:test@localhost:5432/fish_traceability"
$env:JWT_SECRET_KEY = "test-only-secret"
python -m pytest -q
```

The test fixtures mock/override persistence; this test command does not require the database URL above to be reachable. For a separate live connectivity check, configure `backend/.env` and run:

```powershell
python -c "from app.database import engine; c=engine.connect(); print(c.exec_driver_sql('SELECT 1').scalar()); c.close()"
```

The current review run passed **60 tests**. Re-run the command on the commit being submitted; test counts can change as the suite evolves.

## GitHub and submission checklist

- [ ] Push the finished code and documentation to the repository shared with the judges.
- [ ] Keep a meaningful commit for each day you work; do not combine all work into one final upload.
- [ ] Keep `README.md`, feature status, screenshots, setup instructions, and demo accounts current.
- [ ] Confirm `backend/.env` is ignored and `.env.example` contains placeholders only.
- [ ] Run migrations and the demo on a fresh development database.
- [ ] Run `python -m pytest -q` and record the result for the submitted commit.
- [ ] Complete the missing items in [Known limitations](#known-limitations) before claiming full compliance.

## Known limitations

- Dependencies are not pinned in a lockfile, so a fresh install may resolve newer package versions.
- The automated test suite primarily uses mocked persistence; it does not replace a live PostgreSQL workflow check.
- Check the current workflows against the full assignment brief, particularly six-hour cold-chain gaps, current-weight updates after processing, shipping locks, and complete certificate review/issuance gates.
- The JSON vessel-create endpoint does not currently translate duplicate registration/licence database errors into a client-friendly conflict response; the browser form handles this case.
- The Admin user page is a directory; creating users and changing roles/sites are not yet available as admin workflows.
- The mock payment providers are EVC Plus and Zaad only; eDahab is not included.
- Some modules, classes, and helper functions still lack complete purpose/inputs/outputs/error docstrings. The module reference documents the architecture and main interfaces, but this code-level documentation requirement needs a final sweep.
- The committed-history sample currently shows work on 5 and 8 November 2026; it does not by itself prove a commit on every day worked. GitHub publication and judge access must be checked separately.
- The templates load Tailwind from its CDN, which emits a development-use warning; there is no compiled local Tailwind asset pipeline.
