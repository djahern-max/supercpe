# superCPE.com

A NASBA-aligned self-study CPE platform. A licensed CPA watches a narrated
video course, answers review questions between segments, takes a qualified
assessment, and on passing receives a certificate that satisfies Section 9 of
the 2026 Statement on Standards for CPE Programs.

Courses are not authored here. They arrive as **course packages** exported by
the separate `video-tool` repo (local, not deployed). superCPE ingests, reviews,
measures, publishes, delivers, and documents. See `docs/course-package.md` for
the contract between the two repos; it is the only thing they share.

## Lineage
abacadaba (../abacadaba, and its docs in the project) was the learning
experiment that preceded this. Treat it as a rough draft: read its
COMPLIANCE.md and its solutions to a problem before solving the same problem
here, and reuse its Standards locators, but write superCPE fresh. Do not copy
files across. Where abacadaba's COMPLIANCE.md records a gap, that gap is a
requirement here, not an inheritance.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Postgres 16
- Frontend: React 18 + Vite, plain JavaScript (no TypeScript), CSS Modules
- Video storage: DigitalOcean Spaces (S3-compatible) via boto3, presigned URLs
- Local Postgres runs in Docker

## Layout
    backend/            FastAPI app
    frontend/           Vite React app
    docs/               Standards PDFs and the course-package contract
    current-feature.md  the ONE feature being built right now
    CHANGELOG.md        completed features, append only, newest at the bottom
    COMPLIANCE.md       Standards locator -> feature -> code -> known gap
    ROADMAP.md  phases and the feature sequence; read before building

## Workflow, read this first
1. `current-feature.md` is the single source of truth. Build exactly what it
   describes.
2. Do not build outside the feature's scope. If you hit something needed but out
   of scope, finish the feature and list it at the end of your response.
3. Every feature that touches a Standards requirement reads the cited paragraph
   in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf` before writing
   code. The summary in current-feature.md tells you which paragraphs matter;
   it does not replace them.
4. When every acceptance criterion passes, append a `CHANGELOG.md` entry in the
   format below and say the feature is done. Never edit or delete a past entry.
   If a past entry was wrong, write a new entry saying so.
5. Update `COMPLIANCE.md` whenever a feature changes what a locator requires or
   how it is satisfied. If it does not, say so explicitly in the changelog.

## Changelog entry format
    ## NNN — Feature name
    Shipped: YYYY-MM-DD

    **What changed**
    - ...

    **Standards touched**
    - 7.02.6 — one line on what this feature does about it

    **Decisions**
    - ...

    **Known gaps**
    - ...

## Conventions
- snake_case in Python and the database, camelCase in JS, PascalCase for
  components.
- API routes live under /api/v1.
- Every model change ships with its Alembic migration in the same change.
  Autogenerate does not write CHECK constraints; add them by hand.
- Anything that reaches a stored credit, score, or duration uses `Decimal` or
  integers, never float.
- Numbers NASBA chose (50, 180, 1.85, 0.2, question floors, passing score) are
  named constants in `app/constants/`, never inline numerals.
- Derived state (stale, published, complete) is computed from timestamps and
  content, not stored as booleans that can drift.
- Secrets go in .env, never committed. Add new vars to .env.example too.
- Prefer small readable code over clever code. Justify any new dependency.

## Commands
    docker compose up -d
    cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
    cd frontend && npm run dev
    cd backend && pytest
