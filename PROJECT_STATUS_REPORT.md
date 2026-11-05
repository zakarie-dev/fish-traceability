# Fish Traceability Project Status Report

**Review date:** 5 November 2026  
**Scope:** Compared the project brief with the files present in this workspace. This is a source and test review, not a live-system or security audit.

## Executive summary

The project has a working foundation: a FastAPI application, PostgreSQL schema and migrations, bilingual templates, role-aware authentication, dashboard queries, and core lot genealogy/recall logic. The highest-value technical challenge—traversing lot ancestry/descendants and conserving weights during splits—is implemented and has automated test coverage.

The project is **not yet complete against the brief**. Several features exist only as database tables or service methods and are not connected to user workflows. Server-side role and landing-site checks, audit logging, temperature breach handling, processing, consignment management, and certificate eligibility checks are notable gaps.

**Verification:** `python -m pytest -q` completed with **33 passed** and two dependency deprecation warnings. Tests use mocked/isolated persistence; they do not establish that the configured live database is reachable. Per the project owner's statement, the database connection is considered working, but it was not independently tested during this review.

## Feature status

| Area | Status | Evidence and remaining work |
|---|---|---|
| Application architecture | Partial | FastAPI routes, services, repositories, SQLAlchemy models, and Jinja templates are present. Some page handlers in `backend/app/main.py` still query/write through the database session directly, rather than delegating to the service/repository layers. |
| Login and roles | Partial | JWT login, bcrypt password hashing, and four role values are implemented. Some API operations enforce Admin; most HTML workflows only require any authenticated user. Enforce role and site assignment on the server for each action. No sensitive-action audit log was found. |
| Relational schema, migrations, seed data | Mostly done | Versioned PostgreSQL scripts define the core related tables and Somali sample locations/users/vessels/species. See `backend/migrations/`. Add or update schema as missing workflows are implemented. |
| Lot genealogy and split/merge | Core logic done; workflows partial | Recursive ancestor/descendant queries, split weight conservation, loss-reason validation, same-species merge, and recall propagation are implemented. Split and merge are not consistently exposed as role-restricted workflows; merge has no visible route/form. Existing tests cover conservation, merge, lineage, and recall. |
| Vessel registry | Partial | Admin-only vessel creation, uniqueness constraints, fields, and a vessel list are present. Catch creation does not enforce licence validity, and no near-expiry warning or complete vessel-management workflow was found. |
| Landing sites and catches | Partial | Landing-site records and demo seed data exist; a catch form creates a catch and lot. Site assignment enforcement, site administration, inactive-site behavior, protected-species warning/blocking, catch/landing times, and first-temperature capture remain incomplete. |
| QR labels and reprints | Not implemented as specified | Certificate generation embeds a QR code, but per-lot printable labels and reprint logging were not found. |
| Processing | Not implemented as a workflow | A processing-step table exists, but no service or user-facing action was found to record steps, calculate yield, update lot weight, or warn about low filleting yield. |
| Cold chain | Partial | Temperature readings can be entered and stored. The form currently records readings with `is_breach=False`; threshold detection, chilled/frozen rules, six-hour gap alerts, breach review, and temperature charts still need implementation. |
| Inspections | Partial | A form can save grade and pass/fail. Inspector-only enforcement, freshness checks, notes/photos entry, reinspection after a breach, and reliable export eligibility checks are missing or incomplete. |
| Consignments | Partial | Listing and schema exist. Create/edit/remove-lot/shipping-lock workflows, passed-lot and unique-lot constraints, and calculated weights/species were not found. |
| Export certificates | Partial | A PDF endpoint and QR generation exist. Certificate issuance does not appear to enforce passed inspections or open temperature breaches; the PDF does not yet include all required inspection, catch-area, and temperature-summary details. |
| Public trace | Mostly done | Public trace displays ancestry, catch/vessel details, processing and temperature records, and downstream consignments. The public view avoids owner phone numbers and prices. Extend it as missing processing/cold-chain workflows are added. |
| Dashboard | Done for baseline | Dashboard aggregates come from database queries and provide species and landing-site chart data. |
| Somali and English | Partial | Translation dictionaries and a language switch exist, with a matching-key test. Verify every screen/message and translate the certificate PDF; check the real UI on phone and laptop sizes. |
| Simulated payments and SMS | Partial | Adapter interfaces and a mock payment implementation/SMS outbox exist. There is no complete payment/receipt or SMS-trigger workflow; the payment adapter currently supports EVC Plus and Zaad, not eDahab. |
| Tests and CI | Baseline substantially met | 33 tests pass locally and CI runs pytest. Expand coverage as workflows are added. CI is configured for pushes to `main`; consider running it for pull requests too. |
| Documentation and submission | Partial / unverified | `README.md` has setup, test, and demo-account information, but lacks the required complete feature status, architecture/module reference, database diagram, screenshots, limitations, and complete demo instructions. It also says 15 test modules, while this run collected 33 passing tests. No `.git` metadata exists in this workspace, so GitHub sharing and commit history cannot be verified. |

## Recommended work order

Work in dependency order; the database connection is not included as a blocker.

1. **Close authorization and audit gaps.** Add server-side role checks and officer-to-site assignment checks for every write workflow. Record sensitive actions with actor, action, and timestamp. This should precede expanding operational workflows.
2. **Finish catch and vessel rules.** Enforce active site assignment, licence expiry, protected species, and required catch/landing details; add the licence-expiry warning and admin site/species management.
3. **Complete lot operations.** Expose merge safely; add processing steps with weight/yield validation and current-weight updates. Add lot label generation and reprint logging.
4. **Make cold-chain and inspection rules real.** Calculate temperature breaches and reading gaps; require review/reinspection where needed; capture inspection criteria and prevent unpassed or unreleased lots from export.
5. **Implement consignments and certificate gates.** Create/manage consignments, enforce one-consignment-per-lot and shipping lock, calculate totals, and issue/revoke certificates only under the specified conditions. Complete PDF contents and trace QR behavior.
6. **Finish simulated integrations and usability.** Add the payment receipt and SMS outbox screens/flows, support eDahab alongside EVC Plus and Zaad, complete Somali coverage, and test responsive layouts.
7. **Strengthen verification and submission.** Add focused tests for each new rule and end-to-end demo checklist; update README/module and schema documentation; add screenshots; publish/verify the GitHub repository and regular commit history.

## Key files reviewed

- [README.md](./README.md)
- [backend/app/main.py](./backend/app/main.py)
- [backend/app/models.py](./backend/app/models.py)
- [backend/app/services/lot_service.py](./backend/app/services/lot_service.py)
- [backend/app/services/traceability_service.py](./backend/app/services/traceability_service.py)
- [backend/app/services/certificate_service.py](./backend/app/services/certificate_service.py)
- [backend/migrations/001_init.sql](./backend/migrations/001_init.sql)
- [backend/migrations/004_lot_workflows.sql](./backend/migrations/004_lot_workflows.sql)
- [.github/workflows/ci.yml](./.github/workflows/ci.yml)
