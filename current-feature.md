# current-feature.md — Prove Stripe against production before the flip

Feature number: next in the CHANGELOG.md sequence (assign when writing the
entry; 025 was the site header).

## Goal

Make it possible to run a complete Stripe checkout against the live production
server — real DNS, real TLS, real Caddy routing, real signature verification —
while `site_mode` is still `coming_soon` and the keys are still test keys. And
make it impossible to open the site with those test keys still installed.

Two changes, and they pull in opposite directions on purpose: relax the gate on
the one route where it buys nothing, and tighten the gate on the one condition
it never checked.

## Why

021's opening-day checklist has the first real Stripe transaction happening at
step 8, after the flip. Everything that can go wrong in the transport — a Caddy
route that doesn't reach the API, a signing secret pasted with a trailing
newline, a webhook endpoint Stripe disabled weeks ago for failing — would be
discovered there, on the open site, with the waiting list about to be mailed.
That is the wrong place to find out.

Nothing about that transport requires live money. Everything except the money
can be proven months earlier, if the webhook can reach the handler.

## What this reverses, and the argument for it

018's acceptance item 5 says: "router walk green, allowlist untouched." This
feature touches the allowlist. That is a deliberate reversal of a deliberate
decision and the changelog must say so in those words.

The argument. 009 gave the reason for the gate: the refusal is 404 rather than
401 "so the closed site does not advertise what is behind it." That property is
about not disclosing course facts, prices, or the existence of a catalog to an
anonymous visitor — the same instinct 015 and 024 acted on.

`POST /api/v1/stripe/webhook` discloses none of that. It accepts a signed
payload and returns an acknowledgement. It reveals no course, no price, no
participant, no credit figure. An unsigned request is refused by signature
verification, which is a stronger gate than site mode, not a weaker one. The
only thing the exemption reveals is that supercpe.com has a Stripe integration,
which the checkout redirect will announce to every customer anyway.

So the exemption does not weaken the property the gate exists to protect. Verify
this claim rather than trusting this paragraph: read 009's
`require_site_open_or_session` and 015's router-walk test before writing code,
and if the mechanism turns out to protect something this argument missed, stop
and say so instead of proceeding.

Note also what does **not** need exempting: `POST /api/v1/checkout` already
works in `coming_soon` for a signed-in participant, because the gate passes on
"site open **or** a valid session of any role." Only Stripe is sessionless. One
route, one allowlist entry.

## In scope

1. Webhook route exempt from the coming-soon 404.
2. A live-key requirement on the site-open gate, and on preflight.
3. Recording Stripe's `livemode` on the payment row.
4. OPERATIONS.md "Payments (018)" — the section 018 specified and never got.

## Out of scope — flag, don't build

- Any change to checkout refusal logic, the refund rule, enrollment creation, or
  webhook idempotency. 018's decisions stand, including the deliberate one that
  a refund does not void an enrollment.
- Live keys, account activation, bank account, Stripe Tax, invoices, Products
  catalog, coupons.
- Exempting any other 018 route. Checkout and the status endpoint stay behind
  the session-or-open gate.
- A "test mode" flag, a seeded test participant, or any code path that behaves
  differently because a transaction is a test. `livemode` is recorded and
  displayed, never branched on.
- Deleting or hiding test rows. Payments and completions have no delete path and
  this feature does not add one.

## Locators

- 009's `require_site_open_or_session` (`app/deps.py` or nearby) and the
  `INTENTIONALLY_PUBLIC` allowlist 015 introduced
- 015's router-walk test — the one that asserts every route 404s anonymously in
  `coming_soon` unless allowlisted
- `app/services/stripe_gateway.py` (or whatever 018 named the boundary module)
- `app/services/site.py` — `site_open_blockers()` / `launch_findings`
- `app/cli.py` — the `preflight` command `deploy.sh` runs before migrations
- 012's prod config validation, wherever `payments_not_configured` was added
- `backend/alembic/versions/a9d21c5b7e30_stripe_checkout.py` — the payments table
- `frontend/src/pages/AdminPayments/`

## Data model

One migration: `payments.livemode` boolean, nullable (existing rows predate the
column and there are none in production; do not backfill a guess).

Set from the Stripe object as reported, never inferred from the key prefix — the
same rule 018 applied to amount and currency. A test transaction is then
permanently and honestly distinguishable in the record without anything being
deleted, which is what 9.02's never-delete posture requires of us. Docstring says
exactly that.

## Tasks

### 1. Recon — report before editing

- How the webhook route is gated today: the dependency, and whether it is applied
  per-route or to a whole router.
- Where `INTENTIONALLY_PUBLIC` lives, what is in it, and what the router-walk
  test asserts about entries in it.
- What status and body the webhook returns for an unsigned request today.
- Whether `preflight` can reach the database — does it read any DB value now, or
  only the env file?
- Whether the gateway already captures `livemode` from the Stripe object.
- How `/admin/payments` builds its dashboard links, and whether a test-mode id
  would link to the wrong dashboard URL.

### 2. Webhook exemption

- Add the webhook route to `INTENTIONALLY_PUBLIC` with a comment giving the
  argument above in two sentences, not a cross-reference.
- Its behavior is otherwise unchanged: unsigned is refused with the **same status
  and the same body as today**. Do not add a hint, a reason, or a route name to
  that response.
- New test: in `coming_soon`, an unsigned POST is refused exactly as it is at
  `open`, and a signed event is processed exactly as it is at `open`. Assert the
  two mode cases are byte-identical.
- New test, in the spirit of 003/015/016: no webhook response body in either mode
  contains a course title, code, price, credit figure, or the string "National
  Registry".

### 3. Live keys required to open

Two checks, two places, because they answer two different questions.

**The gate.** `site_open_blockers()` gains a finding: `coming_soon → open` is
refused when `STRIPE_SECRET_KEY` or `STRIPE_PUBLISHABLE_KEY` is not a live key.
Message names both the finding and the offending variable, in the existing 422
`{"errors": [...]}` shape. This is the check that matters — the flip is the
moment test keys become dangerous.

**Preflight.** When `site_mode` is already `open` and the configured keys are not
live, preflight fails, naming the variable. This catches the regression of
someone deploying test keys onto an already-open site. `deploy.sh` runs preflight
before migrations with the old version still serving, so the failure mode is a
refused deploy, not an outage. If recon finds preflight cannot reach the database,
say so and put this check at API boot instead, and explain the choice in the
changelog.

Detection is by key prefix (`sk_live_` / `pk_live_`) and nothing else. Do not call
Stripe to ask. A network call in a config validator is a new failure mode for no
gain.

`STRIPE_WEBHOOK_SECRET` has no live/test prefix distinction — it cannot be checked
this way, and the runbook's swap step (task 5) is the control instead. Say so in
the finding's comment so the asymmetry does not read as an oversight.

**Test env.** Conftest currently satisfies `payments_not_configured` with dummy
keys. Those dummies must now be `sk_live_`/`pk_live_`-shaped for the open-mode
fixtures, and a test asserting the refusal must use test-shaped ones. Do not
weaken the check to keep the fixtures as they are.

### 4. Admin surface

- `/admin/payments` shows `livemode` per row — a quiet "Test" marker on
  `livemode = false`, not a badge that shouts.
- If recon shows dashboard links are built for live mode only, make the URL
  respect `livemode` so a test id opens the sandbox dashboard rather than 404ing
  in the live one.

### 5. OPERATIONS.md — "Payments (018)"

018 specified this section and it was deferred as not build-blocking. Write it
now, as steps that were actually executed during this feature:

1. Creating the Stripe account: LLC, EIN, address, industry.
2. Statement descriptor set to match `sponsor_profile.name`, and why — a CPA who
   does not recognize the charge disputes it.
3. Sandbox keys, and the restricted-key scopes the live secret will need
   (Checkout Sessions write; Payment Intents, Charges, Refunds read). Name them
   concretely so launch day is copy-work.
4. **Registering the webhook endpoint twice.** A sandbox endpoint pointing at
   `https://supercpe.com/api/v1/stripe/webhook` for this feature's verification,
   and a separate live endpoint at the same URL at flip time. **They have
   different signing secrets.** `STRIPE_WEBHOOK_SECRET` must be swapped in the
   same edit as the two keys, or every live event fails signature verification
   while the dashboard shows delivery attempts and the site shows nothing. Put
   this in bold in the runbook; it is the single most likely launch-day failure.
5. The production verification run (task 6).
6. The refund runbook 018 asked for: do the refund in Stripe, watch the
   refunded-with-active-enrollment flag appear, decide about the enrollment per
   the published policy. State plainly that the flag is not a bug.
7. What preflight and the open gate each refuse, and the message each gives.

Update 021's opening-day checklist step 4 to say the transport was proven in
advance and what remains is the key swap plus one live smoke purchase.

### 6. The verification run — do this, then write down what happened

Not a test; an operator procedure this feature exists to enable. Run it on
production before writing the changelog, and record the date and the result.

1. `/srv/supercpe/.env` gains the three sandbox values. Site stays `coming_soon`.
2. Deploy. Preflight passes — site is not open, so the live-key check is silent.
3. Register the sandbox webhook endpoint at the production URL. Send a test event
   from the dashboard. It should be accepted, not 404.
4. Sign in as a participant, buy a published course with `4242 4242 4242 4242`.
5. Confirm: the payment row goes `pending → paid` with `livemode = false`, exactly
   one enrollment exists with a one-year expiry, `/purchase/success` stops polling
   and links to the player.
6. Replay the event from the dashboard. Nothing changes.
7. Refund in Stripe. The payment goes `refunded`, the enrollment survives, the
   admin flag appears.
8. Void the test enrollment through the admin action. The payment row stays —
   that is correct, it is an honest record of a test transaction and `livemode`
   says so.
9. Attempt `coming_soon → open`. It must refuse, naming the test keys.
10. Remove the three values from `.env`, deploy, confirm `/health` green.

Step 9 is the one that proves this feature did both of its jobs.

## Acceptance

1. Router walk green with exactly one allowlist addition; the test names it.
2. Unsigned webhook request: identical refusal in both modes. Signed event:
   identical processing in both modes.
3. No course fact and no Registry string in any webhook response, either mode.
4. `coming_soon → open` refused with test keys, naming the variable; succeeds with
   live-shaped keys in the test env.
5. Preflight fails on an open site with test keys, naming the variable.
6. `livemode` recorded from the Stripe object and rendered in `/admin/payments`.
7. Full suite green; count reported and higher than 025's.
8. The task 6 run completed on production, with its date and outcome in the
   changelog and OPERATIONS.md.

## Known gaps to expect

- Stripe disables webhook endpoints after sustained delivery failures. The
  sandbox endpoint registered here may be disabled by flip time if it sits idle
  and failing; the runbook should say to check it rather than assume it.
- Nothing verifies that `STRIPE_WEBHOOK_SECRET` belongs to the same mode as the
  keys. The runbook's swap step is the only control. If a cheap check exists —
  comparing `livemode` on the first received event against the key prefix, and
  logging loudly on mismatch — note it as a candidate, do not build it here.
