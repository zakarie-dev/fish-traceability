# API and Module Reference

This reference reflects the routes and modules in the current repository. API responses can also be inspected interactively at `/docs` while the app is running.

## HTTP interface

### JSON/API endpoints

All API routes use the same local FastAPI application. Endpoints marked authenticated accept a Bearer access token from `POST /auth/login`. The vessel and merge APIs return JSON; the certificate route returns a PDF.

| Method and path | Access | Request | Success response | Main errors |
|---|---|---|---|---|
| `GET /auth/login` | Public | None | `303` redirect to `/login` | — |
| `POST /auth/login` | Public | JSON `{ "email": "...", "password": "..." }`; form submissions are also accepted | JSON `{ "access_token": "...", "token_type": "bearer" }`, or an HTTP-only cookie and redirect for a form | `401` invalid credentials, `422` invalid body, `503` database unavailable |
| `POST /vessels` | Admin | JSON `VesselCreate`: `name`, `reg_number`, `license_number`, `license_expiry`, `owner_name`, `owner_phone?`, `home_port`, `length_m?`, `engine_power?`, `gear_type` | `201` and a `VesselResponse` | `401` missing/invalid token, `403` wrong role, `422` invalid fields; duplicate-number database errors are not yet normalized by this API handler |
| `POST /lots/merge` | Admin or Processor | JSON `{ "lot_ids": ["uuid", "..."] }` (at least two distinct lot IDs) | JSON `{ "merged_lot_id": "uuid" }` | `401`, `403`, `404` missing lot, `400` invalid list or species mismatch |
| `GET /trace/{lot_code}` | Public | Lot code in path | `LotTraceResponse` with ancestor lots, catches/vessels, handling records, and forward consignments | `404` unknown lot |
| `POST /recall/{lot_id}` | Admin or Inspector | Lot UUID in path; no body | `RecallResponse` with affected lot IDs and buyers/destinations | `401`, `403`, `404` unknown lot |
| `GET /consignments/{consignment_id}/certificate.pdf` | Admin or Exporter (browser login) | Consignment UUID in path | PDF download | `401`, `403`, `404` unknown consignment, `409` empty consignment |

`LotTraceResponse` and `RecallResponse` are defined in [`backend/app/schemas.py`](../backend/app/schemas.py). API authentication and role dependencies live in [`backend/app/dependencies.py`](../backend/app/dependencies.py).

### Browser pages and form actions

Browser pages require the login cookie except for `/login`, `/auth/login`, `/trace`, and the JSON public trace endpoint. Successful form submissions normally redirect with `303`; validation errors render the form again with an error message.

| Method and path | Access | Purpose / submitted fields |
|---|---|---|
| `GET /login` | Public | Sign-in form |
| `GET /dashboard` | Authenticated | Database-backed summary and analytics |
| `GET /landing-sites` | Authenticated | Landing-site directory and Admin creation form |
| `POST /landing-sites` | Admin | `name`, `region`, optional paired `gps_lat` and `gps_lng` |
| `GET /users` | Admin | User and assigned-site directory |
| `GET /vessels` | Authenticated | Vessel directory and Admin creation form |
| `POST /vessels/form` | Admin | `name`, `reg_number`, `license_number`, `license_expiry`, `owner_name`, `home_port`, `gear_type` |
| `GET /catches` | Authenticated | Catch-entry form |
| `POST /catches` | Authenticated | `vessel_id`, `species_id`, `weight`, `catch_area`, `catch_date`, `landing_date`, `landing_site_id`, `officer_id` |
| `GET /lots` | Authenticated | Search lot inventory; optional `q` query |
| `GET /lots/{lot_id}` | Authenticated | Lot detail, operations, histories, and label links |
| `POST /lots/{lot_id}/split` | Processor | Comma/newline-separated `child_weights`, `loss_weight`, optional `loss_reason` |
| `GET /lots/merge-selection` | Admin or Processor | Lot selection screen for merging |
| `POST /lots/merge-form` | Admin or Processor | Repeated `lot_ids` form values |
| `POST /lots/{lot_id}/recall` | Admin or Inspector | Recall a lot and its descendants |
| `POST /lots/{lot_id}/processing` | Processor | `step_type`, `weight_in`, `weight_out` |
| `POST /lots/{lot_id}/temperatures` | Authenticated | `temp_celsius`, `temperature_type` (`Chilled`/`Frozen`), `location` |
| `POST /lots/{lot_id}/inspections` | Inspector | `result`, `grade`, `inspector_id` |
| `GET /lots/{lot_id}/label` | Authenticated | Printable lot-label page |
| `GET /lots/{lot_id}/label/qr.png` | Authenticated | PNG QR code for the public trace URL |
| `GET /consignments/new` | Admin or Exporter | Consignment form with currently eligible lots |
| `POST /consignments` | Admin or Exporter | `buyer_name`, `destination_country`, `shipping_date`, `container_number`, repeated `lot_ids` |
| `GET /consignments` | Authenticated | Consignment directory |
| `GET /trace` | Public | Public lot-code lookup page; optional `lot_code` query |
| `GET /processing` | Authenticated | Processing activity list |
| `GET /temperature-logs` | Authenticated | Temperature activity list |
| `GET /inspections` | Authenticated | Inspection activity list |
| `GET /profile` | Authenticated | Current account details |
| `GET /settings` | Authenticated | Language/preferences screen |
| `GET /logout` | Authenticated | Clear login cookie and redirect to `/login` |
| `GET /payments` | Authenticated | Mock mobile-money form; optional `receipt` query |
| `POST /payments` | Authenticated | `provider` (`EVC Plus`/`Zaad`), `phone_number`, positive `amount` |
| `GET /sms-outbox` | Authenticated | Queued mock SMS messages |

The app validates submitted values and enforces the role shown above in server-side handlers. The current implementation is a browser application; not every HTML workflow is exposed as a JSON API.

## Module map

### Application and shared infrastructure

| Module | Responsibility |
|---|---|
| [`backend/app/main.py`](../backend/app/main.py) | Creates the FastAPI app, renders Jinja pages, handles browser forms, language selection, and UI workflow orchestration. |
| [`backend/app/config.py`](../backend/app/config.py) | Loads backend `.env` settings and validates access to database/JWT configuration. |
| [`backend/app/database.py`](../backend/app/database.py) | Creates the SQLAlchemy engine/session factory and yields request-scoped sessions. |
| [`backend/app/models.py`](../backend/app/models.py) | SQLAlchemy models corresponding to the PostgreSQL tables. |
| [`backend/app/schemas.py`](../backend/app/schemas.py) | Pydantic request/response types, constraints, and role enum. |
| [`backend/app/dependencies.py`](../backend/app/dependencies.py) | Resolves the current user from a bearer token or browser cookie and provides role checks. |
| [`backend/app/security.py`](../backend/app/security.py) | Bcrypt password hash and verification helpers. |
| [`backend/app/translations.py`](../backend/app/translations.py) | English/Somali translation dictionaries and lookup helper. |
| [`backend/app/adapters.py`](../backend/app/adapters.py) | Payment and SMS protocols plus mock implementations; mock SMS is stored in the outbox. |

### HTTP routers

| Module | Responsibility |
|---|---|
| [`backend/app/routes/auth.py`](../backend/app/routes/auth.py) | JSON and HTML login handling. |
| [`backend/app/routes/vessels.py`](../backend/app/routes/vessels.py) | Admin-only JSON vessel creation. |
| [`backend/app/routes/lots.py`](../backend/app/routes/lots.py) | JSON lot merge endpoint. |
| [`backend/app/routes/traceability.py`](../backend/app/routes/traceability.py) | Public JSON lot trace and role-protected recall endpoint. |
| [`backend/app/routes/certificates.py`](../backend/app/routes/certificates.py) | Authenticated PDF certificate download and audit event. |

### Business services

| Module | Responsibility |
|---|---|
| [`backend/app/services/auth_service.py`](../backend/app/services/auth_service.py) | Credential verification, JWT issue/decode, and user lookup. |
| [`backend/app/services/vessel_service.py`](../backend/app/services/vessel_service.py) | Vessel creation through the vessel repository. |
| [`backend/app/services/lot_service.py`](../backend/app/services/lot_service.py) | Transactional lot split and merge validation, graph links, and audit calls. |
| [`backend/app/services/traceability_service.py`](../backend/app/services/traceability_service.py) | Backward lineage reports and forward recall propagation. |
| [`backend/app/services/consignment_service.py`](../backend/app/services/consignment_service.py) | Export-eligible lot selection and transactional consignment creation. |
| [`backend/app/services/certificate_service.py`](../backend/app/services/certificate_service.py) | PDF traceability certificate generation and QR embedding. |
| [`backend/app/services/dashboard_service.py`](../backend/app/services/dashboard_service.py) | Combines repository aggregates for the dashboard. |
| [`backend/app/services/audit_service.py`](../backend/app/services/audit_service.py) | Adds sensitive-action audit records to the current transaction. |

### Data access, templates, and tests

| Location | Responsibility |
|---|---|
| [`backend/app/repositories/`](../backend/app/repositories/) | Reusable user, vessel, lot-lineage, and dashboard queries. |
| [`templates/`](../templates/) | Jinja2 pages and reusable UI components. |
| [`backend/migrations/`](../backend/migrations/) | Numbered PostgreSQL schema/data migration scripts; run in numeric order. |
| [`tests/`](../tests/) | Pytest unit/integration-style tests; most persistence is mocked or dependency-overridden. |
| [`backend/tests/`](../backend/tests/) | Additional backend UI form tests. |
| [`backend/seed_demo_data.py`](../backend/seed_demo_data.py) | Additive, confirm-gated showcase dataset seeder for a development database. |

The service/repository split is not yet complete in every page handler: some orchestration and database queries remain in `main.py`. See the README limitations before claiming strict separation for all screens.
