# Learner Metrics — Phased Implementation Plan

## Context

The goal is to build a new multi-tenant SaaS application at `/home/azureuser/Projects/learner-metrics/` that helps NIH and other training programs track and report on grant and publication metrics. The app is architected by combining:

- **Multi-tenant foundation** from `/home/azureuser/Projects/runway/` (RLS, RBAC, unit hierarchy, Google OAuth, Alembic, React/Vite/Zustand)
- **NIH reporter integration** from `/home/azureuser/Projects/learner-metrics/dept_dashboard/` (profile ID lookup, project sync, NIH projects UI)
- **New capabilities**: Full ORCID API integration + PubMed E-utilities for publication tracking

Stack: FastAPI + SQLAlchemy 2.0 async + asyncpg + PostgreSQL + Alembic, React 19 + TypeScript + Vite + TailwindCSS + Zustand, Podman containers.

Environments: dev (local) → staging → production (blue-green).

---

## Project Layout

New code lives directly in `/home/azureuser/Projects/learner-metrics/`:

```
learner-metrics/
├── backend/                     # FastAPI app
│   ├── alembic/versions/
│   ├── scripts/
│   ├── models.py
│   ├── main.py
│   ├── context.py               # Tenant context var
│   ├── database.py              # Async session + RLS setup
│   ├── auth_service.py          # Google OAuth + JWT
│   ├── auth_utils.py
│   ├── config.py
│   ├── schema_service.py        # Schema inheritance
│   ├── nih_service.py           # NIH RePORTER API client
│   ├── orcid_service.py         # ORCID public API client
│   ├── pubmed_service.py        # PubMed E-utilities client
│   ├── requirements.txt
│   ├── alembic.ini
│   └── Dockerfile / Dockerfile.prod
├── frontend/                    # React 19 + Vite + TailwindCSS
│   ├── src/
│   │   ├── store/authStore.ts
│   │   ├── api/client.ts
│   │   ├── pages/
│   │   └── components/
│   ├── package.json
│   └── Dockerfile / Dockerfile.prod
├── nginx/
│   ├── nginx.dev.conf
│   ├── nginx.staging.conf
│   └── nginx.prod.conf          # Blue-green upstream switcher
├── docker-compose.yml           # Dev
├── docker-compose.staging.yml
├── docker-compose.prod-blue.yml # Backend :8001 / Frontend :5001
├── docker-compose.prod-green.yml # Backend :8002 / Frontend :5002
├── .env.example
├── Description.md
└── ImplementationPlan.md
```

---

## Phase 0 — Scaffolding & Infrastructure

**Goal:** Runnable skeleton with all environments wired up before any business logic.

### 0.1 Backend skeleton
- Create `backend/` with FastAPI app, health endpoint (`GET /health`), config via Pydantic `BaseSettings`
- Set up `backend/alembic.ini` and `backend/alembic/env.py` for async SQLAlchemy (copy pattern from `runway/backend/alembic/`)
- `backend/requirements.txt` — key packages: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `python-jose`, `google-auth`, `httpx` (for ORCID/PubMed/NIH)
- `backend/config.py` — port from `runway/backend/config.py`, trim Stripe/SAML for now
- `backend/context.py` — copy exactly from `runway/backend/context.py` (ContextVar tenant isolation)
- `backend/database.py` — copy exactly from `runway/backend/database.py` (`get_db` sets RLS; `get_db_no_rls` for auth)

### 0.2 Frontend skeleton
- Create `frontend/` with Vite — React + TypeScript
- Install: TailwindCSS v3, Zustand, axios, react-router-dom
- Create `frontend/src/store/authStore.ts` — copy from `runway/frontend/src/store/authStore.ts`
- Create `frontend/src/api/client.ts` — copy from `runway/frontend/src/api/client.ts` (adds `Authorization` + `X-Tenant-ID` headers)

### 0.3 Podman + Nginx setup
- `docker-compose.yml` (dev): services `backend`, `frontend`, `db` (postgres:16), `network_mode: host`
- `docker-compose.staging.yml`: override with staging env, ports 8010/5010
- `docker-compose.prod-blue.yml`: backend port 8001, frontend port 5001
- `docker-compose.prod-green.yml`: backend port 8002, frontend port 5002
- `nginx/nginx.prod.conf`: upstream block pointing to active color; reload script `scripts/switch-color.sh` to change nginx upstream and reload
- `backend/Dockerfile` and `backend/Dockerfile.prod`
- `frontend/Dockerfile` and `frontend/Dockerfile.prod`

### 0.4 Environment files
- `.env.example` documents all required variables
- Variables: `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `VITE_API_URL`, `VITE_GOOGLE_CLIENT_ID`, `NCBI_API_KEY`

**Verification:** `podman-compose up` starts three containers, `GET /health` returns 200, frontend loads at localhost:5173.

---

## Phase 1 — Multi-Tenant Foundation

**Goal:** Full auth, tenant isolation, unit hierarchy, and RBAC — ported from runway.

### 1.1 Core database models (`backend/models.py`)
Port from `runway/backend/models.py` — keep only what's needed, drop Stripe/billing tables for now:
- `Tenant` — id, name, domain, slug, status, ui_config (JSONB), created_at
- `Identity` — id, email, password_hash (nullable), google_sub (nullable), created_at (global, no RLS)
- `TenantMembership` — identity_id, tenant_id, user_id (global, no RLS)
- `Unit` — id, tenant_id, parent_id, name, unit_level, tree_path, active (RLS-enabled)
- `User` — id, tenant_id, identity_id, email, first_name, last_name, unit_id, is_active, attributes (JSONB), created_at (RLS-enabled)
- `UserUnitAssignment` — id, tenant_id, user_id, unit_id, privilege (ADMIN/FULL/PARTIAL/VIEW), depth, is_cascading (RLS-enabled)
- `ResourceSchema` — id, tenant_id, unit_id, resource_type, schema_definition (JSONB) (RLS-enabled)
- `AuditLog` — id, tenant_id, actor_id, resource_type, resource_id, action, changes (JSONB), created_at (RLS-enabled)

### 1.2 Migrations
- Initial migration: create all Phase 1 tables
- RLS migration: enable RLS and create `tenant_isolation` policies on all tenant-scoped tables
- Seed migration: create initial `system` tenant

### 1.3 Auth endpoints
Port from `runway/backend/main.py` — Google OAuth 2-step flow:
- `POST /auth/google/identify` — verify Google token, look up/create Identity, return available tenants
- `POST /auth/google/authenticate` — for selected tenant, find/create User + TenantMembership, issue JWT
- `POST /auth/switch-tenant` — switch active tenant, reissue token
- `GET /auth/tenants` — list tenants available to current identity
- `GET /users/me` — current user profile

### 1.4 RBAC privilege resolver
Copy from `runway/backend/main.py`:
- `get_unit_privilege(user_id, unit_id, db)` — resolves highest cascading privilege from tree path
- `has_permission(required_privilege, unit_id_param)` — FastAPI Depends factory

### 1.5 Tenant, unit, user endpoints
- Tenant CRUD (admin only, no-RLS session)
- `POST /tenants/{tenant_id}/admin` — provision first admin user
- Unit CRUD with tree_path management
- User CRUD with RBAC checks
- `GET /users/me/privilege/{unit_id}` — check own privilege

### 1.6 Schema inheritance service
Copy from `runway/backend/schema_service.py`:
- `get_merged_schema(db, tenant_id, unit_id, resource_type)` — hierarchical merge
- Schema CRUD endpoints

### 1.7 Frontend auth + navigation
- `LoginPage.tsx` — Google Sign-In button; on success calls `identify` then `authenticate`
- `authStore.ts` state: token, tenantId, tenantName, user, availableTenants
- `App.tsx` with React Router: protected routes check `authStore.token`
- `UnitManagement.tsx` — port from runway
- `UserManagement.tsx` — port from runway

**Verification:** Google login works, unit hierarchy creates correctly, RBAC blocks unauthorized access.

---

## Phase 2 — NIH Grants Module

**Goal:** Port NIH RePORTER integration from dept_dashboard, adapted for multi-tenancy.

### 2.1 NIH model additions
Add to User: `nih_profile_id: Optional[int]`, `nih_reporter_last_updated: Optional[datetime]`

New table `NIHReporterProject`:
- id, **tenant_id** (RLS), appl_id, project_title VARCHAR(300), project_num VARCHAR(30), core_project_num VARCHAR(30), user_id (FK), fiscal_year, total_costs, project_end_date, project_details JSONB, created_at

### 2.2 NIH service (`backend/nih_service.py`)
Port and async-ify from `dept_dashboard/backend/main.py:273-414`:
- `lookup_nih_profile(first_name, last_name, state)` — calls NIH RePORTER API v2
- `sync_user_nih_projects(session, tenant_id, user)` — 10-year lookback, upserts by `appl_id`

### 2.3 NIH endpoints
- `GET /nih/lookup` — profile lookup (requires FULL privilege)
- `POST /users/batch-nih-lookup` — auto-assign profile IDs (requires ADMIN)
- `POST /users/{user_id}/sync-nih-projects` — sync single user (requires FULL)
- `POST /users/sync-all-nih-projects` — sync all users in tenant (requires ADMIN)
- `GET /nih/projects` — list with filters: user_id, search, current_funding, pagination

### 2.4 Frontend NIH pages
Port from `dept_dashboard/frontend/src/components/`:
- `NIHProfileModal.tsx` — name + state search, select profile ID to assign
- `NIHProjectsPage.tsx` — grouped by `core_project_num`, collapsible rows, tooltips with abstract/costs

**Verification:** Admin can look up NIH profile ID, sync projects, view grouped project list.

---

## Phase 3 — ORCID Integration

**Goal:** Full ORCID public API — look up researcher iD and retrieve their works.

### 3.1 Publication model
New table `Publication`:
- id, tenant_id (RLS), user_id (FK), pmid VARCHAR(20) nullable, doi VARCHAR(200) nullable, title VARCHAR(500), journal VARCHAR(200), pub_year INT, pub_date DATE nullable, authors TEXT, source ENUM('orcid','pubmed','both','manual'), orcid_put_code VARCHAR(50) nullable, raw_data JSONB, created_at, updated_at
- Unique constraints on `(tenant_id, user_id, pmid)` and `(tenant_id, user_id, doi)`

Add to User: `orcid_id: Optional[str]`, `orcid_last_updated: Optional[datetime]`

### 3.2 ORCID service (`backend/orcid_service.py`)
ORCID public API (`https://pub.orcid.org/v3.0`), no auth needed for public records:
- `search_orcid_by_name(first_name, last_name, institution=None)` — search researchers
- `get_orcid_works(orcid_id)` — fetch all works, normalize to Publication dicts
- `sync_user_orcid_publications(session, tenant_id, user)` — upserts by `orcid_put_code`

### 3.3 ORCID endpoints
- `GET /orcid/search` — search by name/institution
- `PUT /users/{user_id}/orcid` — assign `orcid_id` + optionally update name
- `POST /users/{user_id}/sync-orcid` — sync publications
- `POST /users/sync-all-orcid` — batch sync all users with orcid_id

### 3.4 Frontend ORCID components
- `ORCIDLookupModal.tsx` — mirrors NIHProfileModal pattern
- Publications appear on `PublicationsPage.tsx`

---

## Phase 4 — PubMed Integration

**Goal:** PubMed E-utilities integration with per-user stored queries and optional interactive tester.

### 4.1 PubMed service (`backend/pubmed_service.py`)
NCBI E-utilities (`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`), uses `NCBI_API_KEY`:
- `search_pubmed(query, retmax=500)` — esearch, returns PMIDs
- `fetch_pubmed_records(pmids)` — efetch XML, returns normalized Publication dicts
- `build_author_query(first_name, last_name, orcid_id=None, institution=None, custom_query=None)` — constructs PubMed query string
- `sync_user_pubmed_publications(session, tenant_id, user)` — uses `user.pubmed_query`, upserts by PMID; merges with ORCID records (sets source='both' on match)

Add to User: `pubmed_query: Optional[str]`

### 4.2 PubMed endpoints
- `POST /pubmed/test-query` — dry-run query, returns count + first 10 results (no DB write)
- `POST /users/{user_id}/sync-pubmed` — sync using stored query
- `POST /users/sync-all-pubmed` — batch sync all users with a pubmed_query
- `GET /publications` — list with filters: user_id, source, year_range, search, pagination

### 4.3 Frontend publications pages
- `PublicationsPage.tsx` — list grouped by year, source badges (ORCID/PubMed/Both), filters
- `PubMedQueryEditor.tsx` — stored query field, "Test Query" button shows preview panel, "Save & Sync" button

**Verification:** Publications from both ORCID and PubMed sync correctly. Same paper from both sources shows as 'both'. Interactive query tester shows results without writing to DB.

---

## Phase 5 — Metrics Dashboard & Reporting

**Goal:** Aggregate views and export functionality for training program reporting.

### 5.1 Metrics endpoints
- `GET /metrics/grants` — summary: total projects, costs by fiscal year and user
- `GET /metrics/publications` — summary: total pubs, by year, user, source
- `GET /metrics/users/{user_id}` — per-user: grant timeline, publication list, sync status

### 5.2 Dashboard page
- `Dashboard.tsx` — summary cards + trend charts (recharts), unit-scoped per RBAC

### 5.3 Investigator profile page
- `InvestigatorProfile.tsx` — NIH projects (grouped), publications (by year), sync status, edit controls for NIH ID / ORCID iD / PubMed query

### 5.4 Exports
- `GET /exports/grants.csv` — tenant/unit-scoped grants
- `GET /exports/publications.csv` — tenant/unit-scoped publications
- Both require FULL privilege

---

## Phase 6 — Production Hardening

**Goal:** Blue-green deployments, staging pipeline, operational resilience.

### 6.1 Blue-green deploy script (`scripts/deploy.sh [blue|green]`)
1. Build + start target color containers
2. Health check until 200
3. Update `nginx/nginx.prod.conf` upstream to target ports
4. `nginx -s reload`
5. `scripts/rollback.sh` available for instant revert

### 6.2 Staging environment
- `docker-compose.staging.yml`, `scripts/deploy-staging.sh`, `scripts/smoke-test.sh`

### 6.3 Resilience
- NIH/ORCID/PubMed: retry with exponential backoff (3 retries), NCBI rate limit compliance
- Structured JSON logging + request timing middleware
- `GET /health` returns DB check + version

### 6.4 CLAUDE.md
Project-specific guidance: commands, architecture, environment setup, migration workflow.

---

## Source Files to Port

| New file | Source | Notes |
|---|---|---|
| `backend/context.py` | `runway/backend/context.py` | Copy as-is |
| `backend/database.py` | `runway/backend/database.py` | Copy as-is |
| `backend/config.py` | `runway/backend/config.py` | Remove Stripe/SAML |
| `backend/auth_service.py` | `runway/backend/auth_service.py` | Google OAuth only |
| `backend/schema_service.py` | `runway/backend/schema_service.py` | Copy as-is |
| `backend/models.py` | `runway/backend/models.py` | Trim + add NIH/ORCID/PubMed |
| `backend/nih_service.py` | `dept_dashboard/backend/main.py:273-414` | Extract + async-ify |
| `frontend/src/store/authStore.ts` | `runway/frontend/src/store/authStore.ts` | Copy as-is |
| `frontend/src/api/client.ts` | `runway/frontend/src/api/client.ts` | Copy as-is |
| `frontend/src/pages/LoginPage.tsx` | `runway/frontend/src/pages/LoginPage.tsx` | Google only |
| `frontend/src/pages/UnitManagement.tsx` | `runway/frontend/src/pages/UnitManagement.tsx` | Copy as-is |
| `frontend/src/pages/UserManagement.tsx` | `runway/frontend/src/pages/UserManagement.tsx` | Add NIH/ORCID fields |
| `frontend/src/components/NIHProfileModal` | `dept_dashboard/frontend/src/components/NIHProfileModal.tsx` | Adapt |
| `frontend/src/pages/NIHProjectsPage.tsx` | `dept_dashboard/frontend/src/components/NIHProjects.tsx` | Adapt |

---

## Key Architectural Decisions

1. **`nih_profile_id`, `orcid_id`, `pubmed_query` as explicit User columns** — first-class integration fields, not JSONB custom attributes
2. **Single `publications` table** merging ORCID + PubMed — `source` enum tracks origin; dedup by PMID then DOI
3. **`httpx` not `requests`** for all external API calls — async-compatible
4. **ORCID public API only** (no OAuth) — sufficient for reading public works
5. **PubMed query stored on User** — each investigator has a custom query string for specificity
6. **Blue-green via nginx upstream reload** — zero-downtime, instant rollback, single server

---

## Phased Delivery Summary

| Phase | Deliverable | Depends on |
|---|---|---|
| 0 | Runnable skeleton, all environments | — |
| 1 | Auth, tenants, units, RBAC | Phase 0 |
| 2 | NIH grants module | Phase 1 |
| 3 | ORCID integration | Phase 1 |
| 4 | PubMed integration | Phase 3 |
| 5 | Metrics dashboard, exports | Phases 2 + 4 |
| 6 | Production hardening, blue-green | Phase 5 |

> Phases 2 and 3 can be built in parallel once Phase 1 is complete.
