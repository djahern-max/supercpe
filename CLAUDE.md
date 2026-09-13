# superCPE.com

A NASBA-aligned self-study CPE platform. A licensed CPA reads a study guide
(text sections; words ÷ 180 drive credit under 7.02.6), answers review
questions placed between sections, optionally watches supplemental video
clips that count only as additional learning (7.02.7), takes a qualified
assessment, and on passing receives a certificate that satisfies Section 9
of the 2026 Statement on Standards for CPE Programs. Video-only packages are
still supported, but text is the primary format; never assume a lesson has
a video. See docs/decisions/2026-09-01-text-first.md.

Courses are not authored here. They arrive as **course packages** exported by
the separate `video-tool` repo (local, not deployed). superCPE ingests, reviews,
measures, publishes, delivers, and documents. See `docs/course-package.md` for
the contract between the two repos; it is the only thing they share. Credit
math, question minimums, and readiness findings belong here, never in
video-tool.

## Lineage
abacadaba (../abacadaba) was the learning experiment that preceded this.
Reference only. superCPE's own CHANGELOG.md, COMPLIANCE.md, and
docs/decisions/ are now the record; consult abacadaba only when a spec
says to. Do not copy files across.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, psycopg
  (`postgresql+psycopg://`), Postgres 16
- Frontend: React 18 + Vite, plain JavaScript (no TypeScript), CSS Modules,
  React Router 7, vitest, oxlint
- Object storage: DigitalOcean Spaces (S3-compatible) via boto3, presigned URLs
- Production: DigitalOcean droplet, Docker Compose (`deploy/`), Caddy in
  front, managed Postgres; `deploy/deploy.sh` runs preflight, migrates,
  and polls health
- Local Postgres runs in Docker on host port 5433

## Layout
    backend/            FastAPI app; app/constants/ holds every NASBA number
    frontend/           Vite React app
    deploy/             docker-compose.yml, Caddyfile, deploy.sh
    docs/               Standards PDFs, course-package.md, OPERATIONS.md,
                        decisions/ (one dated file per architectural decision)
    current-feature.md  the ONE feature being built right now
    CHANGELOG.md        completed features, append only, newest at the bottom
    COMPLIANCE.md       Standards locator -> feature -> code -> known gap
    ROADMAP.md          phases, feature sequence, improvement notes; read
                        before building

There is exactly one `current-feature.md` in the repo. Numbered copies of
past specs live outside the repo; if you find one inside it, stop and ask
which is live rather than guessing.

## Workflow, read this first
1. `current-feature.md` is the single source of truth. Build exactly what it
   describes. If it has a Task 0 (recon), answer every question in your
   response before writing code; the answers go in the changelog entry.
2. Do not build outside the feature's scope. If you hit something needed but
   out of scope, finish the feature and list it at the end of your response.
   "Report, do not build" means exactly that.
3. Every feature that touches a Standards requirement reads the cited
   paragraph in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`
   before writing code, and the changelog names the printed page it was
   read on. Never cite a paragraph from memory. The summary in
   current-feature.md tells you which paragraphs matter; it does not replace
   them.
4. Before writing the changelog entry: typecheck, lint, backend `pytest`,
   frontend tests, and `frontend/scripts/sync_brand.py --check` all pass,
   and `git status --porcelain` is clean apart from the feature's own
   changes.
5. When the acceptance criteria the build session can run pass, append
   the CHANGELOG.md entry and say the feature is done. Criteria that
   need the operator (a production deploy, a browser walkthrough, a
   dashboard step, a real reviewer) are listed under Known gaps as
   "not yet run by the operator"; the operator may later append a short
   verification entry, or not. Never edit or delete a past entry. If a
   past entry was wrong, write a new entry saying so.
6. Update `COMPLIANCE.md` whenever a feature changes what a locator requires
   or how it is satisfied. If it does not, say so explicitly in the
   changelog.
7. Reversing a recorded decision (a changelog Decision, a docs/decisions
   file, a ROADMAP rule) is allowed only when the spec asks for it, and the
   changelog names it as a reversal of the specific earlier decision.
8. Never run `alembic downgrade`. Fix forward only.

## Changelog entry format
    ## NNN — Feature name
    Shipped: YYYY-MM-DD

    **What changed**
    - ...

    **Standards touched**
    - 7.02.6 — one line on what this feature does about it (page read)

    **Decisions**
    - ...

    **Known gaps**
    - ...

## House rules that protect records (9.02)
- Accounts, enrollments, reviews, attempts, payments: deactivated, voided,
  or superseded — never deleted. Financial rows outlive `RETENTION_YEARS`.
- Snapshots are the truth: a certificate renders from
  `certificate_snapshot`, never from today's course or sponsor row.
- Published courses are immutable; content changes mean unpublish,
  re-review, republish. Participants keep the package versions they
  enrolled on.
- No fictitious reviewer, SME, or review records in production, ever.
- Until launch, production data is test data: dropping and recreating the
  database is a routine step and needs no retention discussion. Retention
  starts with the first real participant or reviewer record.

## House rules that protect participants
- No answer key reaches the browser. Choices carry keys and text, never
  `is_correct`; feedback comes only from the grading endpoint, only after
  an answer. A failed assessment shows nothing per question (6.01.2).
- Gates are server-side. A locked section's text is not in the payload.
- New public routes 404 anonymously in `coming_soon` and are not added to
  `INTENTIONALLY_PUBLIC` in `tests/test_site.py` unless the spec says so
  (rule 7 above). Nothing rendered while coming-soon names a course, a
  price, a credit figure, or "National Registry".
- "National Registry" and the sponsor statement render only behind
  `may_claim_registry`.
- Site mode, email, and Stripe: the open gate (`launch_findings`) is
  satisfied by real configuration, never weakened to fit a test.

## Conventions
- snake_case in Python and the database, camelCase in JS, PascalCase for
  components. Table names are plural.
- API routes live under /api/v1; errors are 422 `{"errors": [...]}`.
- Every model change ships with its Alembic migration in the same change.
  Autogenerate does not write CHECK constraints; add them by hand.
- Anything that reaches a stored credit, score, or duration uses `Decimal` or
  integers, never float. Money is integer cents; dollars exist only in
  rendering.
- Numbers NASBA chose (50, 180, 1.85, 0.2, question floors, passing score)
  and numbers the sponsor chose (re-takes, retention years, review
  cadence) are named constants in `app/constants/`, never inline numerals,
  each with the paragraph or the word "ours" beside it.
- Derived state (stale, published, complete, exhausted, voided) is computed
  from timestamps and content, not stored as booleans that can drift.
- Constant-response rule: registration, resend, verification, and any
  route that could reveal whether an account exists answer one shared
  constant body.
- Secrets go in .env, never committed. Add new vars to .env.example too;
  production config validation (012) learns every new var.
- Prefer small readable code over clever code. Justify any new dependency
  in requirements.txt or package.json.
- Tests never touch the network; Stripe, SMTP, and Spaces are stubbed at
  their boundary modules.

## Commands
    docker compose up -d
    cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
    cd frontend && npm run dev
    cd backend && pytest
    cd frontend && npm test
    cd backend && python -m pyflakes app tests        # lint (Python)
    cd frontend && npm run lint                       # lint (oxlint)
    backend/.venv/bin/python frontend/scripts/sync_brand.py --check   # brand assets in sync
Production commands and the diagnostic sequence are in docs/OPERATIONS.md;
do not run them from a build session.
