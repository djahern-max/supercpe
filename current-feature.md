# Feature 030a — Google sign-in preview on a closed site

030 shipped Sign in with Google, but two deliberate rules stack against
proving it on production: 009's coming-soon gate (anonymous requests
404) and 026's open gate (`coming_soon → open` refuses test Stripe
keys). Together they mean the button cannot appear on supercpe.com
until live Stripe keys exist — opening day. 026's own argument applies:
opening day is the wrong place to find a transport problem (wrong
origin on the OAuth client, a Caddy rate-limit line that does not
match, an env value with a trailing space).

This feature lets the operator, and only the operator, walk Google
sign-in on the closed production site. It is config-only: with the
config unset, every behavior is byte-identical to 030.

## What this feature decides

1. **An allowlist, not an exemption.** `GOOGLE_PREVIEW_EMAILS` — a
   comma-separated list of email addresses, case-folded, default empty.
   While the site is `coming_soon` and the request carries no session,
   `POST /api/v1/auth/google` verifies the token first and proceeds only
   if the token's verified email is on the list; every other outcome —
   bad token, unverified email, email not listed — is the gate's bare
   404, byte-identical to today's. Anonymous visitors learn nothing;
   the closed catalog stays closed. Google's Testing-mode test-user list
   also limits who can complete the popup, but that is an operator
   promise; the allowlist is what a test can assert.
2. **Once past the allowlist, coming-soon behaves exactly as open.**
   The three account branches, the constant 401 for refusals (admin,
   reviewer, deactivated, already linked elsewhere), the session cookie,
   the `MeOut` shape — none of it forks on site mode.
3. **The config route answers while closed only when the list is
   non-empty.** `GET /api/v1/auth/google/config` in `coming_soon`,
   anonymous: 404 when `GOOGLE_PREVIEW_EMAILS` is empty (today's
   answer); the client id when it is not. A client id is public by
   construction — it ships in the page's JavaScript — so answering it
   reveals only that a Google client exists, not a course, a price, or
   a participant. Same argument 026 made for the webhook.
4. **Button on `/login` only.** `GoogleSignIn` renders whenever the
   config returns a non-null client id, regardless of `siteFace()`.
   `/login` already exists while closed (admins use it). `Register` is
   unchanged: it renders only at open, so the preview never creates a
   "sign up" surface on a closed site — a Google-created account is the
   endpoint's third branch either way.
5. **Not part of the open gate; inert at open.** At open the list is
   never consulted. Preflight prints a note in both modes and never
   refuses over it. Unsetting it is an opening-day step.
6. **Acceptance 1 becomes checkable.** 030 could not confirm "the
   accounts admin list shows the row with `email_verified_at` set"
   because `AccountOut` does not carry it. `AccountOut` gains
   `email_verified_at` and `signin_methods` (same derivation as
   `MeOut`), read-only, shown on `/admin/accounts`. Small; if Task 0
   finds it larger than two columns and a test, report and skip it.

## Read before building

- 009 (`require_site_open_or_session`, why the refusal is 404 not 401).
- 015 (`INTENTIONALLY_PUBLIC` and the router-walk test) and 026's
  Decisions (the only prior exemption and the argument that justified
  it — this feature must make the same kind of argument in its own
  words, in the allowlist comment, not by cross-reference).
- 030 (`services/google_identity.verify`,
  `auth_service.sign_in_with_google`, `GOOGLE_SIGN_IN_FAILED`,
  `src/components/GoogleSignIn/`, `src/auth/googleIdentity.js`, and
  `GoogleSignIn.test.jsx`'s "coming-soon `/login` never asks for the
  config" — that assertion is deliberately reversed here; see Tests).
- 012's config validation and the preflight note pattern in
  `backend/app/cli.py`.
- OPERATIONS.md "Google sign-in (030)" and the Opening day checklist
  (step 6 is 030's).

## In scope

1. `GOOGLE_PREVIEW_EMAILS` config, validation, preflight note.
2. Allowlist branch on the two Google routes while `coming_soon` and
   sessionless.
3. `GoogleSignIn` render rule keyed on the config response alone.
4. `AccountOut.email_verified_at` and `AccountOut.signin_methods`.
5. OPERATIONS.md and Opening day additions.

## Out of scope (report, do not build)

- Password login or 017 self-registration on a closed site.
- Any preview for `/register`, the catalog, or course pages.
- A general "preview mode" or staff-preview cookie for the whole site.
- Changing 026's open gate, or making the allowlist part of it.
- Any change to the constant-response bodies or to the 404's body.
- 017a (password reset) — still unbuilt; still not this feature.

## Locators

- `backend/app/config.py`, `backend/.env.example`,
  `backend/app/cli.py` (preflight).
- `backend/app/routers/auth.py` (`google_config`, `google_sign_in`),
  `backend/app/services/auth.py` (`sign_in_with_google`).
- Wherever `require_site_open_or_session` and `INTENTIONALLY_PUBLIC`
  live (Task 0 names the files).
- `backend/app/schemas/...` for `AccountOut`; `/admin/accounts` router
  and the `AccountsAdmin` (or equivalent) page.
- `frontend/src/components/GoogleSignIn/`, `frontend/src/pages/Login*`.
- `docs/OPERATIONS.md`, `CHANGELOG.md`.

## Data model

None. No migration.

## Tasks

### 0. Recon — report before editing

1. How `require_site_open_or_session` is applied to the two Google
   routes (per-route `dependencies=[...]`, as 030's router shows) and
   what the router-walk test asserts about a route that leaves it.
   Confirm the bare 404's exact status and body so the allowlist
   refusal can be asserted byte-identical.
2. Whether `stored_site_mode()` / the site-mode read used by the gate
   is callable from inside a route handler without a second query
   pattern; name the function to reuse.
3. How `config.py` parses list-valued settings today (any existing
   comma-separated var to copy the pattern from); how 012's validator
   reports notes vs violations.
4. What `AccountOut` carries and where `/admin/accounts` renders it;
   whether `email_verified_at` is on the `Account` model under that
   name.
5. How `GoogleSignIn.test.jsx` asserts "coming-soon `/login` never asks
   for the config", so the reversal is one assertion, not a rewrite.

### 1. Config

- `GOOGLE_PREVIEW_EMAILS` (optional, default empty). Parsed to a
  frozenset of case-folded, stripped, non-empty addresses. Not part of
  any all-or-nothing group. Meaningless without `GOOGLE_CLIENT_ID`:
  validation notes (does not refuse) "GOOGLE_PREVIEW_EMAILS is set but
  GOOGLE_CLIENT_ID is not; it has no effect."
- Preflight note, both modes: "note: GOOGLE_PREVIEW_EMAILS lists N
  address(es)" or "is not set". When `site_mode` is `open` and the
  list is non-empty, the note adds "the site is open; the list is
  inert — unset it (Opening day step 6)". A note, never a refusal.

### 2. Backend

- Both Google routes drop `require_site_open_or_session` from their
  `dependencies` and are added to `INTENTIONALLY_PUBLIC` with a
  comment giving the argument in two sentences: the config route
  answers a public client id and nothing else; the sign-in route
  refuses with the gate's own 404 unless a Google-verified email is on
  the operator's list, so the closed site still advertises nothing to
  anyone the operator did not name.
- A small helper, one place (`auth` router or a `site_mode` module,
  Task 0 decides): `preview_allowed(db, request) -> bool` returns True
  at open, True with any valid session, else False. The two routes:
  - `google_config`: if `preview_allowed` or the allowlist is non-empty
    → `{"client_id": ...|null}`; else the gate's bare 404 (raise the
    same exception the dependency raises, do not construct a new one).
  - `google_sign_in`: if not `preview_allowed`: call
    `google_identity.verify` on the credential; on any failure, or
    `email_verified` false, or case-folded email not in the allowlist
    → the gate's bare 404. Only then fall through to the existing
    `sign_in_with_google` path unchanged. (The token is verified twice
    on the preview path: once for the allowlist, once inside the
    service. Accept that; it costs a cached-JWKS signature check and
    keeps `sign_in_with_google` untouched. Say so in the changelog.)
- The allowlist path must not create, link, or change any row before
  the allowlist check passes. Assert it.
- `AccountOut` gains `email_verified_at: datetime | None` and
  `signin_methods: list[str]`, derived exactly as `MeOut` does (share
  the helper; do not copy the derivation). `/admin/accounts` shows
  both; no filter, no edit.

### 3. Frontend

- `GoogleSignIn` renders when the config request returns a non-null
  `client_id`. Remove the `siteFace() === OPEN` condition from the
  component. `Login` mounts it in both modes; `Register` is unreachable
  while closed and is not touched.
- GIS `<script>` loading is unchanged: once, lazily, only when the
  config is non-null. On a closed site with the list empty the config
  404s, so nothing loads — the 030 property "coming-soon `/login` never
  loads GIS" survives as "…never loads GIS unless the config answers".
- On the 404 (closed, not listed), the button simply does not render;
  no message. On the constant 401 after a listed email is refused (an
  admin's address on the list, say), 030's generic failure text.
- `/admin/accounts`: two columns, `Verified` (date or "—") and
  `Sign-in` (Password / Google / Password and Google).

### 4. Ops (operator, documented by the build session)

OPERATIONS.md "Google sign-in (030)" gains a subsection **Preview
before open (030a)**: set `GOOGLE_PREVIEW_EMAILS` to the Gmail
address(es) also listed as Test users on the consent screen; deploy;
on `/login` the button appears for everyone but completes only for a
listed address — anyone else gets Google's popup and then nothing
(the 404 renders as no change). Walk acceptance 1 and 2 on production.
Unset and deploy when done, or leave it until the flip. Opening day
step 6 gains a third line: **unset `GOOGLE_PREVIEW_EMAILS`**.

## Tests

Backend (baseline 540):

- Allowlist empty, `coming_soon`, anonymous: both routes return the
  gate's 404, byte-identical to a 030-era snapshot of the same
  requests (status and body). No row created or changed.
- Allowlist non-empty, `coming_soon`, anonymous: config answers the
  client id; sign-in with a stubbed valid token for a listed email →
  participant created, session cookie, `MeOut` shape identical to the
  open-mode response for the same token (assert byte-identical apart
  from ids/timestamps, as 030 asserts across branches).
- Allowlist non-empty, `coming_soon`, anonymous: unlisted email, bad
  token, expired token, wrong audience, `email_verified` false → all
  the gate's 404, byte-identical to each other and to the empty-list
  case; no row created or changed.
- Listed email whose account is admin / reviewer / deactivated →
  the constant 401, not 404 (once listed, refusals look like open).
- Case-folding: `Dane@Example.com` in the env matches a token for
  `dane@example.com`.
- `open` mode: allowlist non-empty vs empty → identical responses
  for every case above (the list is inert).
- With a valid session in `coming_soon`, both routes answer as before
  regardless of the list.
- Router walk green with exactly two `INTENTIONALLY_PUBLIC` additions;
  no other route's gating changed.
- Preflight: note text for set / unset / set-while-open; never a
  violation.
- `AccountOut`: `email_verified_at` and `signin_methods` present and
  derived correctly for the three variants; `/admin/accounts` still
  admin-only.

Frontend (baseline 122):

- `GoogleSignIn.test.jsx`: reverse one assertion — coming-soon `/login`
  now requests the config; when it 404s, no button and no GIS load;
  when it answers, the button renders and GIS loads once. Coming-soon
  landing and `/admin/courses` still never request the config.
- `Login.test.jsx`: a listed-email success in coming-soon routes
  exactly as password login does.
- Admin accounts page renders both new columns for the three variants.

## COMPLIANCE.md rows

None. No Standards paragraph is touched: 9.02 participant records are
unchanged and no locator's requirement or satisfaction moves. The 009
gate property ("a closed site does not advertise what is behind it")
must be argued in the changelog's Decisions in this feature's own
words, and the two `INTENTIONALLY_PUBLIC` comments must carry the
argument, as 026 required of the webhook.

## Acceptance

1. Local, `coming_soon`, `GOOGLE_PREVIEW_EMAILS` unset: `/login` shows
   no Google button; `curl` of both routes returns the 404.
2. Local, `coming_soon`, list = your Gmail (also a consent-screen Test
   user), real client id: `/login` shows the button; sign in as that
   address → `/my/courses`; `/account` says "Sign-in methods: Google";
   `/admin/accounts` shows the row with a verified date and "Google".
3. Local, same config: sign in with a Google account not on the list →
   popup completes, page unchanged, no row created (check the DB).
4. Local: set `site_mode` to open, leave the list set → preflight
   prints the inert note; behavior identical to 030 with the list
   unset.
5. pyflakes, oxlint, both suites green; router walk green with exactly
   two additions.
6. Production, `coming_soon`: set `GOOGLE_CLIENT_ID` and
   `GOOGLE_PREVIEW_EMAILS`, deploy, repeat 2 and 3 on supercpe.com.
   Then repeat 030's acceptance 2 (link a password account). Log the
   run in OPERATIONS.md; this closes 030's Acceptance 7 early.

## When done

Append the CHANGELOG entry (CLAUDE.md rule 5 as relaxed 2026-09-12:
operator-only steps — acceptance 6 and the consent-screen setup —
listed under Known gaps as "not yet run by the operator"). Record in
Decisions: the allowlist-not-exemption choice and the 009 argument;
the double verify on the preview path; the one reversed frontend
assertion and why. Record in Known gaps that 017a is still unbuilt
and that the `Register` page has no preview by design.
