# Feature 030 — Sign in with Google

Participants may create an account and sign in with a Google account
instead of a password. Convenience only: it changes who can sign in
easily, not what an account is, what it records, or what any role may
do. Password sign-in, 017's self-registration, and 017a's reset all
stay exactly as they are.

## What this feature decides

1. **ID-token flow, not the redirect code flow.** The frontend renders
   Google's "Sign in with Google" button (Google Identity Services); on
   success Google hands the browser an ID token; the browser POSTs it to
   superCPE; the backend verifies the token's signature, issuer,
   audience, and expiry against Google's published keys and reads the
   `sub`, `email`, and `email_verified` claims. No client secret, no
   callback route, no OAuth state to keep. One config value:
   `GOOGLE_CLIENT_ID`.
2. **Google is an identity, not a role.** Google sign-in creates
   **participant** accounts only and signs in existing accounts only
   when their role is participant. Admin and reviewer accounts never
   sign in with Google (an operator's Google account compromised is not
   an admin compromise).
3. **Verified-email linking.** If Google reports `email_verified: true`
   and a participant account exists with that email, the first Google
   sign-in links it (`google_sub` set once) and signs it in. Google's
   verification satisfies 017's requirement: a Google-created account
   has `email_verified_at` set at creation. If Google reports the email
   unverified, refuse.
4. **Password becomes optional.** A Google-created account has no
   password. It may set one later through 017a's reset flow (the reset
   email proves the address); password sign-in for an account with no
   password fails the same way as a wrong password (017's constant
   responses).
5. **Optional config group.** `GOOGLE_CLIENT_ID` unset means the button
   does not render and the endpoint answers as if the feature did not
   exist. It does not join the open gate; the site can open without it.
6. **Same site-mode rule as `/register`.** The Google button renders and
   the endpoint accepts only while the site is `open` (or with a
   session, for linking). While coming-soon, the endpoint 404s
   anonymously like every 017 route, and 021's waiting-list invitation
   path stays password-only (reported, not built).

## Read before building

- 009 (accounts, roles, sessions, `require_site_open_or_session`),
  017 (self-registration, `email_verified_at`, the constant-response
  rule and its shared body), 017a (reset), 025/027 (`siteFace()`, the
  login page's "Create account" render rule).
- 022's CSP or security headers in `deploy/Caddyfile`: Google's button
  script loads from `accounts.google.com` and opens an iframe/popup
  from the same origin. Task 0 must find what the headers allow today.
- House rules: derived state; deactivate never delete; constant
  responses on anything that could reveal whether an account exists;
  secrets in `.env` and `.env.example`; a new dependency is justified in
  the changelog.

## Standards

None touched. Identity verification is not a Standards requirement;
9.02's participant records are unchanged (an account row gains one
nullable column). Say so in the changelog and in COMPLIANCE.md's "not
touched" line if the file keeps one; otherwise no row.

## In scope

### 1. Task 0 — establish, then decide scope

Answer each in the changelog before writing code:

1. How does password login set the session (cookie name, flags,
   `SameSite`, the service function)? Google sign-in must call the same
   function, not a copy.
2. What are the current security headers in the Caddyfile (CSP,
   `Cross-Origin-Opener-Policy`, frame rules)? List exactly what must be
   added for `https://accounts.google.com` (script-src, frame-src,
   connect-src, and COOP `same-origin-allow-popups` if COOP is set).
   Smallest change that works; nothing wildcarded.
3. Is `accounts.password_hash` nullable today? If not, the migration
   makes it so, and the password-login path must treat `NULL` as
   "wrong password" with the constant response. Find every place a
   password is verified.
4. Which is the smaller, better-maintained dependency for verifying a
   Google ID token in Python 3.12: `google-auth` (its
   `id_token.verify_oauth2_token`) or verifying the JWT directly with
   `PyJWT` and Google's JWKS? Recommend one, with its transitive
   dependency count. The spec's default is `google-auth`; overrule with
   a reason.
5. Does 017's registration require any field beyond email and password
   (name, state of licensure, terms acknowledgement)? A Google-created
   account must collect the same non-password fields — either on a short
   "finish your account" step after the first Google sign-in, or by
   allowing them empty until first enrollment. Report which and why; if
   the answer is "nothing else is required", say so.
6. Does the frontend test setup (vitest, jsdom) tolerate a component
   that loads an external script? Plan the mock for the GIS global
   (`window.google.accounts.id`).

### 2. Config

- `GOOGLE_CLIENT_ID` (optional, default unset) in `config.py`,
  `.env.example`, and 012's validation with a "configured / not
  configured" note in preflight. Not part of any all-or-nothing group;
  not a readiness finding.
- `GET /api/v1/auth/google/config` (public at open, 404 coming-soon):
  `{ "client_id": "…" }` or `{ "client_id": null }`. The frontend
  renders the button only when non-null. Nothing else is exposed.

### 3. Data model

- `accounts.google_sub` — nullable, unique, set once. Google's `sub` is
  the stable identifier; the email may change on Google's side, `sub`
  does not. Never matched on email after linking.
- `accounts.password_hash` nullable if Task 0.3 finds it is not.
- Hand-written migration. No other change.

### 4. Backend

- `services/google_identity.py` — the boundary module: `verify(id_token)
  -> GoogleIdentity(sub, email, email_verified)` or raises. Verifies
  signature via Google's keys, `iss` in Google's two accepted values,
  `aud == GOOGLE_CLIENT_ID`, not expired. Tests stub this module the way
  018 stubs `stripe_gateway`; no test touches the network.
- `POST /api/v1/auth/google` — body `{ "credential": "<id token>" }`,
  behind `require_site_open_or_session`. In one service function:
  1. `verify`; on any failure → 401 with the constant sign-in-failed
     body.
  2. `email_verified` false → same 401.
  3. Account by `google_sub` → if role participant and active, sign in;
     otherwise the constant 401 (deactivated and non-participant look
     identical to a bad token).
  4. Else account by email (case-folded as 017 does) → if role
     participant and active, set `google_sub`, set `email_verified_at`
     if null, sign in; otherwise the constant 401.
  5. Else create a participant account: email, `google_sub`,
     `email_verified_at = now`, no password, plus whatever Task 0.5
     decided; sign in.
  All three outcomes return the same shape as password login. The
  response never says which branch ran; the changelog's Decisions
  explain why (an attacker with a Google account for `x@y` must not
  learn whether `x@y` has a superCPE account).
- Password login: an account with `password_hash IS NULL` fails with the
  constant wrong-credentials response. 017a's reset works on such an
  account and results in a password (the account then has both).
- Rate limiting: whatever 017 applies to `/login` applies to
  `/auth/google` (Caddyfile rate-limit block or backend limiter —
  Task 0 finds which).
- `/account` payload gains `signin_methods: ["password", "google"]`
  (derived: `password_hash` non-null, `google_sub` non-null). No unlink
  action (out of scope).

### 5. Frontend

- `Login` page: below the form, at `siteFace() === OPEN` and only when
  `client_id` is non-null, an "or" divider and Google's rendered button
  (`google.accounts.id.initialize` + `renderButton`, `ux_mode: "popup"`,
  no One Tap / auto-select). The callback POSTs the credential and, on
  success, routes exactly as password login does. On the constant 401,
  show 017's generic failure text.
- `Register` page: the same button with "or sign up with Google"
  wording; same endpoint (creation is the endpoint's third branch).
- GIS script tag loaded once, lazily, only on those two pages when
  `client_id` is non-null — never in `index.html`, so coming-soon and
  admin pages make no request to Google.
- `/account`: "Sign-in methods: Google" / "Password and Google" from the
  payload; for a Google-only account, a line "To add a password, use
  Forgot password" linking 017a. No settings UI beyond that.
- Task 0.5's "finish your account" step, if needed.

### 6. Ops (operator, documented by the build session)

OPERATIONS.md "Google sign-in (030)": create the OAuth client (Web
application) in Google Cloud Console under a project named for
superCPE; authorized JavaScript origins `https://supercpe.com` and the
local dev origin; **no redirect URIs** (ID-token flow); copy the client
id into the env; the consent screen needs an app name, support email,
and a **privacy policy URL** — note that superCPE's `/policies` are the
8.01 CPE policies, not a privacy policy, and the operator must decide
where a privacy policy lives before publishing the consent screen
(until then the OAuth app stays in Testing mode, which limits sign-in
to listed test accounts — fine for now, a launch-day item). Add both
lines to the opening-day checklist.

## Out of scope (report, do not build)

- Redirect/code flow, refresh tokens, or storing any Google token —
  the ID token is verified and discarded.
- Google sign-in for admin or reviewer roles; any role change by
  Google.
- Unlinking Google from an account; changing the linked Google account.
- One Tap, auto sign-in, Apple or Microsoft sign-in.
- Waiting-list invitation (021) via Google.
- A privacy policy page (flagged in ops; separate feature if needed).
- Any change to 017's verification email, 017a's reset, or the
  constant-response bodies.

## Data model summary

`accounts.google_sub` (nullable, unique); `accounts.password_hash`
nullable. One hand-written migration.

## Tests

Backend (baseline 523):

- `verify` stubbed: valid token for a new email → participant created,
  `email_verified_at` set, no password, session issued, response shape
  identical to password login.
- Existing participant with same email, no `google_sub` → linked, signed
  in, `google_sub` set once (second sign-in matches by `sub`, and a
  changed Google email does not create a second account).
- Existing participant already linked → signed in by `sub`.
- Deactivated participant, admin, reviewer, `email_verified` false,
  invalid token, expired token, wrong audience → all return the same
  constant 401 body (asserted byte-identical across cases).
- `GOOGLE_CLIENT_ID` unset → `/auth/google/config` returns null client
  id; `/auth/google` answers the constant 401 (not 404 — 404 is the
  site-mode answer).
- Password login for an account with `password_hash IS NULL` → the
  constant wrong-credentials response; 017a reset on that account sets a
  password and password login then works.
- Router walk green; `/auth/google` and `/auth/google/config` 404
  anonymously in `coming_soon`; `INTENTIONALLY_PUBLIC` untouched.
- Migration: `google_sub` unique; two accounts cannot share one.

Frontend (baseline 104):

- Login and Register render the Google button only at open and only
  when the config returns a client id; GIS global mocked; a successful
  callback POSTs the credential and routes like password login; a 401
  shows the generic failure text.
- Coming-soon and `/admin` pages never inject the GIS script.
- `/account` renders each `signin_methods` variant.

## Acceptance

1. Local, with a real client id in `.env` and the Cloud project in
   Testing mode with your Google account listed: on `/login`, sign in
   with Google as a new email → land in `/my/courses`; `/account` shows
   "Sign-in methods: Google"; the accounts admin list shows the row with
   `email_verified_at` set.
2. Local: register a password account, then sign in with Google using
   the same email → same account, now linked; `/account` shows both.
3. Local: try Google sign-in with an admin account's email → the generic
   failure; the admin account is unchanged.
4. Local: password login on the Google-only account → generic failure;
   run the reset flow → password login works.
5. Local: unset `GOOGLE_CLIENT_ID` → no button, endpoint 401.
6. pyflakes, oxlint, both suites green; router walk green.
7. Operator: production client id set, Caddyfile headers deployed, repeat
   1 and 2 on production (Testing-mode consent screen, your account).

## When done

Append the changelog entry when 1–6 pass; list 7 under Known gaps as
"not yet run by the operator". Include the Task 0 answers, the exact
header lines added to the Caddyfile, the dependency chosen and why, and
the privacy-policy note for the opening-day checklist. No COMPLIANCE.md
row unless Task 0.5 changed what an account records.
