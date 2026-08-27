# Changelog
Append-only. Newest at the bottom. Never edit or delete a past entry —
if something was wrong, write a new entry saying so.
---

## 001 — Walking skeleton
Shipped: 2026-08-27

**What changed**
- Repo scaffolding: `CLAUDE.md`, `CHANGELOG.md`, empty `COMPLIANCE.md` matrix,
  `.gitignore`, `docker-compose.yml` (Postgres 16 on 5432, named volume,
  credentials from `.env`), root and per-app `.env.example` files
- `docs/` populated with the four Standards PDFs alongside the existing
  `course-package.md`
- Backend: FastAPI app "superCPE API" with CORS from settings,
  pydantic-settings config (`DATABASE_URL`, comma-separated `CORS_ORIGINS`),
  SQLAlchemy 2.0 engine/session/`Base`/`get_db`, `GET /api/v1/health` running
  `SELECT 1` (200 ok / 503 unavailable), Alembic wired to `app.config.settings`
  and `Base.metadata` with `app.models` imported for future autogenerate
- Frontend: Vite React app stripped of boilerplate, `src/styles/global.css`
  design tokens, `src/api/client.js` + `src/api/health.js`, App renders the
  superCPE wordmark and a green "Backend connected" / red "Backend unreachable"
  status pill
- One backend test: `tests/test_health.py` asserts 200 and status "ok"

**Standards touched**
- None — scaffolding.

**Decisions**
- Vite's current template scaffolds React 19; pinned back to React 18 to match
  the documented stack
- Stopped the machine's Homebrew `postgresql@16` service (user-approved): it
  listened on 127.0.0.1:5432 and shadowed the Docker container's port mapping.
  Restart with `brew services start postgresql@16` if another project needs it
- Health endpoint returns the 503 body via `JSONResponse` so the error shape
  bypasses the 200 `response_model`

**Known gaps**
- `COMPLIANCE.md` is empty by design; rows begin with feature 002
