# Changelog

All notable changes to Learner Metrics are documented here.

---

## [0.1.0] — 2026-02-26

Initial build. All phases implemented from scratch.

### Phase 0 — Scaffolding & Infrastructure

- FastAPI backend skeleton with health endpoint, Pydantic `BaseSettings` config, `asyncpg` database setup
- Alembic migration framework with async SQLAlchemy 2.0 pattern
- Vite + React 19 + TypeScript + TailwindCSS + Zustand frontend
- Podman/Docker container setup for dev, staging, and blue-green production
- Nginx configs for all environments (see below)
- `.env` / `.env.example` / `.env.staging` with all required variables
- Deployment scripts: `deploy.sh`, `deploy-staging.sh`, `smoke-test.sh`, `switch-color.sh`

### Phase 1 — Multi-Tenant Foundation

- **PostgreSQL Row-Level Security** — `tenant_isolation` policies on all tenant-scoped tables; `SET LOCAL app.current_tenant` per request
- **Models**: `Tenant`, `Identity`, `TenantMembership`, `Unit`, `User`, `UserUnitAssignment`, `ResourceSchema`, `AuditLog`
- **Alembic migrations**: initial schema (001), RLS policies (002), system tenant seed (003)
- **Google OAuth 2-step auth flow**:
  - `POST /auth/google/identify` — verifies Google token, returns available tenants
  - `POST /auth/google/authenticate` — issues JWT for selected tenant
  - `POST /auth/switch-tenant`, `GET /auth/tenants`
- **RBAC**: `ADMIN(4) > FULL(3) > PARTIAL(2) > VIEW(1)`; cascading via `tree_path` unit hierarchy; `has_permission()` FastAPI Depends factory
- **Platform admin** endpoints: tenant CRUD, provision-admin bootstrap
- **Unit CRUD** with hierarchical `tree_path` management
- **User CRUD** with unit assignment and RBAC checks
- **Schema inheritance service**: `get_merged_schema()` merges parent→child field definitions; parent fields read-only in children
- **Frontend**: Login page (Google Sign-In), sidebar navigation (`DashboardLayout`), Unit Management, User Management pages, Zustand auth store, axios interceptors for `Authorization` + `X-Tenant-ID` headers

### Phase 2 — NIH Grants Module

- **`backend/nih_service.py`**: async NIH RePORTER API client
  - `lookup_nih_profile()` — search by name + state, deduplicates by `profile_id`
  - `sync_user_nih_projects()` — 10-year fiscal year lookback, upserts by `(tenant_id, appl_id)`, stores full JSON in `project_details`
- **`NIHReporterProject` model** with RLS; columns: `appl_id`, `project_title`, `project_num`, `core_project_num`, `fiscal_year`, `total_costs`, `direct_costs`, `indirect_costs`, `project_start_date`, `project_end_date`, `project_details` (JSONB)
- **Endpoints**: `GET /nih/lookup`, `POST /users/{id}/assign-nih-profile`, `POST /users/{id}/sync-nih-projects`, `POST /users/sync-all-nih-projects`, `GET /nih/projects`
- **`NIHGrantsPage.tsx`**: projects grouped by `core_project_num`, collapsible fiscal-year rows, hover tooltips with cost detail, search + investigator filter + active-only toggle
- **`NIHProfileModal.tsx`**: name + state search modal, clickable results to assign profile ID
- **`UserManagement.tsx`**: per-row NIH sync button with inline status message; "Find profile" shortcut for unlinked investigators

### Phase 3 — ORCID Integration

- **`backend/orcid_service.py`**: ORCID public API v3.0 client (no OAuth required)
  - `search_orcid_by_name()` — search by name + optional institution
  - `get_orcid_works()` — fetches all works, retrieves full records for DOI/PMID/author data
  - `sync_user_orcid_publications()` — upserts into `publications` table by `orcid_put_code`; upgrades `source` to `'both'` when a PubMed record already exists
- **Endpoints**: `GET /orcid/search`, `PUT /users/{id}/orcid`, `POST /users/{id}/sync-orcid`, `POST /users/sync-all-orcid`
- **`ORCIDLookupModal.tsx`**: name + institution search, clickable results to assign ORCID iD
- **`UserManagement.tsx`**: ORCID "Find" button per row alongside NIH controls

### Phase 4 — PubMed Integration

- **`backend/pubmed_service.py`**: NCBI E-utilities client
  - `search_pubmed()` — `esearch.fcgi` JSON, returns PMID list
  - `fetch_pubmed_records()` — `efetch.fcgi` XML parse: title, journal, authors, pub date, DOI
  - `sync_user_pubmed_publications()` — uses stored `user.pubmed_query`; deduplicates against existing ORCID records by PMID then DOI; upgrades `source` to `'both'` on match
- **`Publication` model**: `pmid`, `doi`, `title`, `journal`, `pub_year`, `pub_date`, `authors`, `source` (`orcid`/`pubmed`/`both`/`manual`), `orcid_put_code`, `raw_data`; unique constraints on `(tenant_id, user_id, pmid)` and `(tenant_id, user_id, doi)`
- **Endpoints**: `POST /pubmed/test-query`, `PUT /users/{id}/pubmed-query`, `POST /users/{id}/sync-pubmed`, `POST /users/sync-all-pubmed`
- **`PublicationsPage.tsx`**: paginated list grouped by year; source badges (ORCID / PubMed / Both / Manual); PMID and DOI external links; year-range, investigator, and source filters; "Sync ORCID" and "Sync PubMed" buttons
- Optional `NCBI_API_KEY` env var for higher rate limits (10 req/s vs 3 req/s)

### Phase 5 — Metrics Dashboard

- **`GET /metrics/summary`** — returns `{users, investigators, grants, publications, nih_linked, orcid_linked}`
- **`GET /publications`** — paginated, filterable publication list endpoint
- **`Dashboard.tsx`** — live summary cards (Investigators, NIH Grants, Publications, Units); integration coverage progress bars for NIH and ORCID; active modules checklist

### Phase 6 — Production Hardening

- **`CLAUDE.md`** — comprehensive project guide: commands, architecture, API contracts, migration workflow, deployment, data model notes
- **Nginx configs** updated and corrected (see below)
- All backend files pass `ast.parse()` syntax check; frontend passes `tsc --noEmit`

---

## Nginx / Infrastructure

### `nginx/nginx.dev.conf`
- Updated ports from 8020/5020 → **8201/5201**
- Added `Cross-Origin-Opener-Policy: same-origin-allow-popups` header (required for Google Sign-In popup)
- Added `proxy_read_timeout 120s` on API location (NIH/ORCID sync calls can run 30–120s)

### `nginx/nginx.staging.conf`
- Serves app at `/lm/` prefix on a shared port-80 server
- Added `proxy_read_timeout 120s` on API location

### `nginx/nginx.prod.conf`
- **Fixed broken blue-green switching**: replaced inline upstream blocks + fragile `sed` with an `include active-upstream.conf` directive
- Added gzip compression, TLS protocol/cipher hardening, security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)

### `nginx/active-upstream.conf` *(new)*
- Managed exclusively by `switch-color.sh`; initial state: blue (8001/5001)

### `scripts/switch-color.sh`
- Rewritten: overwrites `active-upstream.conf` atomically via `cat >`; no more fragile `sed` on the main config file
- Switching back and forth between colors now works correctly in all cases

### Frontend build for staging
- `vite.config.ts`: `base` reads `VITE_BASE_PATH` env var (defaults to `/`)
- `App.tsx`: `BrowserRouter` reads `VITE_BASE_PATH` as `basename` so routing and asset paths align with the `/lm/` prefix
- `.env.staging`: `VITE_BASE_PATH=/lm/`, `VITE_API_URL=/lm/api`, ports 8010/5010

---

## Ports Reference

| Environment | Backend | Frontend |
|-------------|---------|----------|
| Dev         | 8201    | 5201     |
| Staging     | 8010    | 5010     |
| Prod Blue   | 8001    | 5001     |
| Prod Green  | 8002    | 5002     |
