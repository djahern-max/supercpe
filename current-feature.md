# Current Feature

## Feature 001, Walking skeleton

## Goal
Prove the chain works end to end in the new repo: Postgres, FastAPI, and the
React app talking to each other, with the repo's working agreements and the
Standards documents in place. No product features yet.

This is a port of abacadaba's feature 001, with three differences: the docs
directory is populated from day one, `COMPLIANCE.md` exists as an empty matrix
ready for feature 002 onward, and the changelog uses the structured format in
`CLAUDE.md`.

## In scope
- Repo scaffolding: `CLAUDE.md`, `CHANGELOG.md`, `COMPLIANCE.md`, `docs/`,
  `.gitignore`, `docker-compose.yml`, `.env.example` files
- Backend config, database session, health endpoint, Alembic set up and runnable
- Frontend stripped of Vite boilerplate, global CSS variables, one status banner
- One backend test

## Out of scope
- Any course, lesson, package, question, user, sponsor, or certificate code
- Auth, DigitalOcean Spaces, deployment, domain, TLS
- Porting any abacadaba module beyond what 001 there contained

## Repo tasks
1. Copy the four Standards PDFs into `docs/` with these names:
   - `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`
   - `docs/2026-Explanatory-Memo.pdf`
   - `docs/2024-to-2026-Standards-Crosswalk.pdf`
   - `docs/2024-Fields-of-Study.pdf`
   `docs/course-package.md` is already present; do not modify it.
2. `CHANGELOG.md`: the header block below, then nothing. Feature 001's entry is
   appended when this feature is done.
       # Changelog
       Append-only. Newest at the bottom. Never edit or delete a past entry —
       if something was wrong, write a new entry saying so.
       ---
3. `COMPLIANCE.md`: a title, a one-paragraph scope note saying it maps superCPE
   behavior to the 2026 Standards PDF and nothing else, and an empty table with
   columns `Locator | Requirement | Feature | Where in code | Gap`. No rows.
4. `docker-compose.yml`: Postgres 16, port 5432, named volume, credentials from
   `.env`.
5. Root `.gitignore` covering `.env`, `.venv/`, `node_modules/`, `__pycache__/`,
   `backend/uploads/`, and editor files.

## Backend tasks
1. `backend/.venv`, `backend/requirements.txt` pinned: fastapi, uvicorn[standard],
   sqlalchemy>=2, alembic, psycopg[binary], pydantic-settings, pytest, httpx.
2. `app/config.py`: Settings via pydantic-settings reading `DATABASE_URL` and
   `CORS_ORIGINS` from `backend/.env`. `CORS_ORIGINS` is a comma-separated
   string parsed into a list.
3. `app/db.py`: engine from `DATABASE_URL`, `SessionLocal`, declarative `Base`,
   `get_db` dependency that yields a session and always closes it.
4. `app/main.py`: FastAPI app titled "superCPE API", CORS middleware from
   settings, health router under `/api/v1`.
5. `app/routers/health.py`: `GET /health` executes `SELECT 1` and returns
   `{"status": "ok", "database": "connected"}`; on failure returns 503 with
   `{"status": "error", "database": "unavailable"}`.
6. `app/schemas/health.py`: `HealthResponse` used as the `response_model`.
7. `alembic init alembic` inside `backend/`. `alembic/env.py` reads the URL from
   `app.config.settings`, sets `target_metadata = Base.metadata`, and imports
   `app.models` (create the package with an empty `__init__.py` now so later
   features' autogenerate sees their tables). Leave `alembic.ini`'s
   `sqlalchemy.url` empty.
8. `tests/test_health.py`: httpx + TestClient asserting `GET /api/v1/health`
   returns 200 and status "ok".
9. `backend/.env.example` with both vars and placeholder values.

## Frontend tasks
1. `npm create vite@latest frontend -- --template react`, then delete the
   boilerplate: `App.css`, logo assets, the counter demo.
2. `src/styles/global.css`: CSS custom properties for colors, spacing, radius,
   and font stack. Professional, high-contrast, one accent color. This is a
   product a state board auditor may look at; restrained beats playful. Import
   once in `main.jsx`.
3. `src/api/client.js`: prefixes `import.meta.env.VITE_API_URL`, sets JSON
   headers, throws on non-2xx, returns parsed JSON.
4. `src/api/health.js`: `getHealth()` via the client.
5. `src/App.jsx` + `src/App.module.css`: on mount call `getHealth()`, render the
   superCPE wordmark and a status pill reading "Backend connected" (green) or
   "Backend unreachable" (red).
6. `frontend/.env.example` with `VITE_API_URL=http://localhost:8000`.

## Acceptance criteria
- `docker compose up -d` brings Postgres up on 5432
- `uvicorn app.main:app --reload` starts with no errors
- `curl http://localhost:8000/api/v1/health` returns status ok, database connected
- `alembic upgrade head` runs cleanly (no revisions yet is fine)
- `npm run dev` renders the green "Backend connected" pill at localhost:5173
- `pytest` passes
- `docs/` contains the four PDFs and `course-package.md`
- `git status` is clean after commit; no `.env` is tracked

## When done
Append the 001 entry to `CHANGELOG.md` in the structured format. Under
"Standards touched" write "None — scaffolding." Under "Known gaps" note that
`COMPLIANCE.md` is empty by design. Then stop.
