# Current Feature

## Feature 017, Self-registration and email verification

## Goal
A member of the public can create a participant account with a verified
email address. Verification is the first outbound email superCPE ever
sends, so this feature also builds the email machinery that 019
(certificates) and 021 (invitations) will reuse: one sending service, one
outbound log, a dev backend that costs nothing, and a production backend
that is pure configuration. Like 016, this is **built now and ships at
open** — every new public route 404s in `coming_soon` and nothing is added
to `INTENTIONALLY_PUBLIC`.

## Read before building
002/003 built accounts and auth; 010 built enrollments against
participants. **Read that code first** and fit self-registration into the
existing account model — a role or flag distinguishing participants from
the admin, whatever shape 002 established — rather than a parallel table.
If the existing model resists (e.g. accounts were admin-only by
construction), say what you changed and why in the changelog. Two standing
rules bind everything here: accounts are deactivated, never deleted
(9.02), and the registration/attendance policy 011 published is the
formalized policy 8.01.1 requires — the form links it, it does not restate
it.

## In scope

### 1. Email service
`backend/app/services/email.py`, one interface, two backends chosen by
config:
- **console/dev**: writes the message to the log and to the outbound
  table; used in dev and in every test. No network.
- **smtp**: generic SMTP over TLS from env (`EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`). Provider-agnostic on
  purpose — choosing one is an ops step, recorded in OPERATIONS.md, not a
  code change.
- 012's production config validation learns the email settings: if any
  `EMAIL_*` is set, all must be, and `EMAIL_FROM` must parse as an
  address. Absent entirely is valid config while the site is coming-soon.

### 2. Outbound email log
`email_message` table: kind (e.g. `verification`), recipient, subject,
created_at, and the backend that handled it. Body is **not** stored
(verification links don't belong at rest beyond the token table).
Docstring states these are operational records, not CPE records — same
declaration as 015's waiting list, and the same reasoning: no participant
linkage requirement, no `RETENTION_YEARS`.

### 3. Registration
`POST /api/v1/register` — `{name, email, password, state?}`. State of
licensure is optional, validated against 015's
`constants/jurisdictions.py` when present (020 will want it; don't make
strangers hand it over to get an account). Email lowercased/trimmed with
the auth service's existing shape check; password rules follow whatever
002 established for the hidden login — do not invent a second policy.

**The response never reveals whether the email is known.** Every
well-formed submission gets the identical 200: "check your email."
Branches behind that constant response:
- New email → account created unverified, verification email sent.
- Existing active account → no new account; a "you already have an
  account" email goes to the address instead.
- Existing **deactivated** account → no reactivation, no new account; an
  email telling the holder to contact the sponsor. Reactivation is a
  deliberate human step (9.02 is why the row still exists), not a side
  effect of a form.
This is 015's honeypot philosophy applied to accounts: the response body
is one constant message, enumeration is impossible from the API's shape.

### 4. Verification
- Token: single-use, random ≥256 bits, stored **hashed**, expires in 48
  hours, one active token per account (a resend invalidates the prior).
- `POST /api/v1/verify` with the token: marks the account's
  `email_verified_at`, consumes the token. Expired/unknown/used tokens
  all get the same failure message.
- `POST /api/v1/resend-verification` — same constant-response rule as
  registration.
- An unverified account cannot log in; the login failure message for
  unverified is the same generic failure as wrong-password (no
  enumeration through the login door either).
- Caddy rate limits on register/verify/resend mirroring the login rule.

### 5. Site-mode behavior and the open gate
- `coming_soon`: all 017 public routes 404 anonymously; the 015 router
  walk passes with its allowlist untouched (404-in-coming_soon routes
  pass it automatically, as 016's did).
- `open`: routes public.
- `launch_findings` gains one finding: the email backend must be `smtp`
  with complete settings before `coming_soon → open`. A site that is
  open but cannot send verification email has a registration form that
  lies. Dev/test flips to open keep working by setting dummy SMTP config
  in the test env, not by weakening the gate.
- Admin: a "send test email" action (guarded, swept by 009's walk) so
  the ops runbook can prove the SMTP config before the flip;
  OPERATIONS.md gains the section (choose provider, set env, test-send,
  what the gate refuses without it).

### 6. Frontend
- `/register` (name, email, password, optional state dropdown from the
  jurisdictions list, a link to the published registration policy, the
  constant success message), `/verify` (reads the token from the URL,
  posts it, shows success/failed), and a resend affordance from the
  login page's unverified path — which, per the rule above, looks
  identical to any failed login, so the affordance is a general "didn't
  get your verification email?" link on the login page, not a targeted
  hint.
- The course page's reserved Registration section is **not** wired here.
  Enrollment is created by payment success (018); a register link that
  dead-ends before checkout exists is 018's problem to solve whole.

### 7. Tests and docs
- Constant-response tests: byte-identical 200 bodies across
  new/existing/deactivated cases, with the outbound log asserting which
  email actually went out in each.
- Token lifecycle: verify, reuse-refused, expiry, resend-invalidates.
- Login refusals: unverified indistinguishable from wrong-password.
- Mode matrix; router walk untouched; open-gate refusal without SMTP
  config and success with it.
- Config validation matrix for `EMAIL_*`.
- COMPLIANCE.md: extend the 8.01.1 row (registration flow links the
  published policy); note under 9.02 that self-registered accounts
  inherit deactivate-never-delete unchanged.

## Out of scope
- Payment, checkout, enrollment creation (018).
- Certificate and invitation emails (019, 021) — they reuse the service,
  they are not built early.
- Password reset. If 002 didn't build it for the hidden login, it is its
  own small feature (017a candidate), not a rider — token machinery here
  should be written so reset can reuse it, and that's the whole
  concession.
- Choosing the email provider. Ops decision, OPERATIONS.md records it
  when made.
- Any change to admin/tester login behavior.

## Acceptance
1. In dev, registering shows the constant message, the console backend
   logs a verification email, and following the token verifies the
   account; before verification the account cannot log in.
2. Registering the same email again, or a deactivated account's email,
   returns a byte-identical response; the outbound log shows the
   already-registered / contact-sponsor email respectively; no second
   account row exists.
3. An expired or reused token fails with the same message as an unknown
   one.
4. All public 017 routes 404 anonymously in `coming_soon`; the 015
   router walk is green with no allowlist change.
5. `coming_soon → open` refuses without complete SMTP config, naming the
   finding; succeeds with it (test env).
6. Admin test-email action delivers through the configured backend and
   appears in the outbound log.
7. Full suite green; changelog entry written, carrying the 015
   browser-check date correction if Dane reports one.

## Notes for Claude Code
- The constant-response bodies must be one shared constant, not three
  string literals that happen to match today.
- Hash tokens with a fast cryptographic hash (they're high-entropy;
  bcrypt is for passwords), compare in constant time.
- ROADMAP: mark 017 built ahead of ship; add "password reset (017a?)" to
  Improvement notes if 002 has none.
