# Current Feature

## Feature 018, Stripe checkout

## Goal
A verified participant can pay for a published course and, on payment
success, an enrollment (010's anchor record) exists with its one-year
clock started. Stripe holds the card; superCPE holds the money's paper
trail. Like 016/017, **built now, ships at open**: every new public route
404s anonymously in `coming_soon`, nothing joins `INTENTIONALLY_PUBLIC`.

## Read before building
010's enrollment creation and expiration are the anchor — read that code
first and call it; do not write a second enrollment constructor. Read the
011 refund/cancellation policy machinery (018 links and obeys it, never
restates it). The 016 course payload and course page grow a price and a
live Registration section here.

## Architecture rules
1. **The webhook is the sole creator of enrollments.** The browser
   returning to a success URL proves nothing; only a
   signature-verified `checkout.session.completed` event creates the
   enrollment. The success page polls for it.
2. **Stripe is a boundary service** (`services/stripe_gateway.py` or
   similar): one thin module owns every Stripe API call and signature
   check. Tests stub this boundary; no test touches the network. The
   real dependency is the official `stripe` Python package.
3. **Stripe Checkout (hosted page), not embedded Elements.** Card data
   never transits superCPE; PCI surface is a redirect.
4. Table naming follows the plural house convention (017's singular
   `email_message` came from the spec, not from Claude Code — this spec
   doesn't name tables).

## In scope

### 1. Price on the course
- Admin-set integer **cents**, USD only, on the course record; editable
  on the admin course page; rendered on the public catalog card and
  course page as dollars.
- **Publish now also requires a price** (> 0). This is a business rule,
  not an 8.01 item — its refusal message says so and it is listed
  separately from the disclosure items in the 422. Rationale: at open,
  "published" must mean "purchasable"; a course page with no way to buy
  is a dead end the reserved section was only ever a placeholder for.
  The 016 admin readiness view gains the finding; the test factory sets
  a price.
- Price is not retroactive: the amount actually charged is recorded on
  the payment row from the Stripe event, not re-derived from the course.

### 2. Payments table
One row per checkout attempt that reached Stripe: account, course,
Stripe checkout-session id (unique), payment-intent id, amount and
currency **as Stripe reported them**, status
(`pending → paid → refunded`, plus `expired` for abandoned sessions if
the expiry webhook is handled), created/updated timestamps. Docstring:
financial records, never deleted, not subject to `RETENTION_YEARS` —
they outlive it.

### 3. Checkout
- `POST /api/v1/checkout` `{course_code}` — requires a logged-in,
  verified participant (verification is what 017's gate was for).
  Refusals, each with a distinct error: course not published; course
  already enrolled **and not expired** (re-purchase after expiry is
  allowed and creates a fresh enrollment — the old one is history, per
  the anchor-record design); a `pending` payment younger than the
  session lifetime exists (return the existing session's URL instead of
  minting another).
- Creates the Stripe Checkout Session server-side: line item from the
  course title and stored price, `metadata` carrying account id, course
  code, and payment row id; success URL `/purchase/success` with the
  session id; cancel URL back to the course page. Stripe's own receipt
  email enabled — superCPE sends no payment email of its own.
- The payment row is written `pending` before the redirect URL is
  returned.

### 4. Webhook
- `POST /api/v1/stripe/webhook` — signature-verified against
  `STRIPE_WEBHOOK_SECRET`; unauthenticated by session (Stripe can't log
  in) but refuses anything unsigned. 404 in `coming_soon` like every
  018 route.
- **Idempotent by event id**: processed event ids are stored; a replay
  answers 200 and does nothing.
- `checkout.session.completed` → mark the payment `paid`, create the
  enrollment via 010 (expiration = one year from now, the standing
  rule), all in one transaction. If the metadata's payment row is
  already `paid`, do nothing (idempotency belt and braces).
- `charge.refunded` (or the dispute equivalent) → mark the payment
  `refunded` and **stop**. The enrollment is not voided automatically:
  whether a refund unwinds access is the published refund policy's
  question and an admin's answer — especially once credit has been
  earned or a certificate issued. The admin payments view flags
  refunded-with-active-enrollment loudly.
- Unhandled event types answer 200 and are ignored by name in a log
  line.

### 5. Success page and enrollment surfacing
- `/purchase/success` polls a small
  `GET /api/v1/checkout/{session_id}/status` (owner-only) until the
  webhook lands, then links to the course player; a spinner with an
  honest "confirming your payment" line, and after ~30s a
  "confirmation is taking longer than usual" state that names the
  support address — webhooks can lag.
- The course page's reserved Registration section goes live at open:
  price + Enroll button when signed in and not enrolled; sign-in/register
  links otherwise (register → 017's flow); "you're enrolled" with a
  player link when enrolled. In `coming_soon` nothing changes (page is
  gated anyway).

### 6. Config, gate, ops
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
  join 012's validation: all-or-nothing, absent entirely valid while
  coming-soon.
- Open gate: new block finding `payments_not_configured` — no
  `coming_soon → open` without complete Stripe config. Test env
  satisfies it with dummy keys in conftest; every test call goes through
  the stubbed boundary.
- Admin: `/admin/payments` — table (account, course, amount, status,
  Stripe ids as links to the Stripe dashboard), the
  refunded-with-active-enrollment flag, and an explicit "void
  enrollment" action (guarded, logged) for when the refund policy says
  access ends. Voiding deactivates per the house deactivate-never-delete
  rule as it applies to enrollments in 010 — read how 010 models
  enrollment state before inventing a new one.
- OPERATIONS.md: "Payments (018)" — create the Stripe account, restrict
  the API key, register the webhook endpoint and capture its secret,
  set the three env vars, test-mode end-to-end with Stripe CLI
  (`stripe listen --forward-to`), what the open gate refuses without
  config, and the refund runbook (do the refund in Stripe, watch the
  flag appear, decide about the enrollment per the policy).

### 7. Tests and docs
- Boundary-stub tests: checkout refusal matrix (unpublished, already
  enrolled, expired-then-repurchase allowed, pending-session reuse);
  webhook creates enrollment exactly once across replays; unsigned
  webhook refused; refund marks payment and does not touch the
  enrollment; success-status endpoint owner-only.
- Publish refusal without price, worded as business rule; open-gate
  refusal/success on Stripe config; mode matrix; 015 router walk green,
  allowlist untouched.
- COMPLIANCE.md: 8.01 item 9's row updated — courses are now actually
  sold for a fee, the refund-policy link is load-bearing; note that
  amount charged is recorded per payment (9.02-adjacent honesty, cite
  only what the Standard actually says after reading it).

## Out of scope
- Sales tax (Stripe Tax — ROADMAP improvement note), coupons,
  subscriptions, multiple currencies, invoicing, self-service refunds.
- Certificate email on completion (019).
- Any change to how completion or certificates work — paying starts the
  clock, nothing else.
- Automatic enrollment voiding on refund (deliberate, see webhook).

## Acceptance
1. Publish refuses a priced-at-zero course as a business rule, separate
   from disclosure items; the factory course publishes with a price.
2. With the stubbed boundary: checkout on a published course returns a
   session URL and a `pending` payment row; the completed-session
   webhook creates exactly one enrollment expiring one year out, and a
   replayed event changes nothing.
3. Re-purchase is refused while enrolled, allowed after the enrollment
   expires, and a live pending session is returned rather than
   duplicated.
4. An unsigned webhook is refused; a refund event marks the payment and
   leaves the enrollment intact, and the admin view flags it; the void
   action ends access and is logged.
5. All 018 public routes 404 anonymously in `coming_soon`; router walk
   green, allowlist untouched; open gate refuses without Stripe config
   and passes with it.
6. Full suite green; changelog entry written (carrying the 015
   browser-check date correction if Dane reports one when feeding this
   spec).
7. Operator, later, not build-blocking: the OPERATIONS.md test-mode
   walkthrough with Stripe CLI on the dev machine.

## Notes for Claude Code
- Amounts are integer cents everywhere in code; dollars exist only in
  rendering.
- The webhook handler must tolerate the payment row being absent
  (metadata pointing at a row a rollback ate): log loudly, answer 200,
  never 500 — Stripe retries 500s forever.
- ROADMAP: mark 018 built ahead of ship; add the Stripe Tax note.
