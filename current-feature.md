# Feature 029 — Annual subscription

Sponsor decisions recorded 2026-09-12. A participant may either buy a
course (018) or hold an **annual subscription**: $149, auto-renewing
through Stripe Billing, unlimited course enrollments while it is
current. Course purchases already made are credited, dollar for dollar,
against the first subscription payment. A lapsed subscriber keeps every
record and simply pays again to resume. Refunds are full, no questions
asked, never pro-rata.

**Prerequisite, not part of this feature:** 026 acceptance 8 (the
Stripe production verification run) must have been performed and
logged before this feature is deployed. Subscriptions ride the same
account, keys, and webhook endpoint. Do not build on an unproven
transport.

## What this feature decides

1. Subscriptions are Stripe Billing subscriptions started through
   Stripe Checkout in `subscription` mode. Stripe owns the renewal
   schedule and the card; superCPE owns the paper trail and the
   entitlement.
2. Entitlement is derived: a subscription is current when its Stripe
   status is `active` and now is before `current_period_end`, both as
   Stripe last reported them. No stored "is subscriber" flag.
3. A subscriber enrolls in a published course with no Stripe call:
   `source="subscription"`, the standing one-year clock from
   enrollment. **A subscription ending does not touch enrollments
   started under it** — each keeps its own year (9.02.2(3)), and a
   subscription-sourced enrollment counts as paid for 028's free
   renewal.
4. Purchase credit: the sum of the account's `paid` (never refunded)
   course payments, not previously credited, applied to the first
   invoice as a one-time Stripe coupon. Capped at the subscription
   price; the first year may cost $0, in which case Stripe still
   collects a payment method for the renewal.
5. Refunds follow 018's rule exactly: the webhook marks, the admin
   decides. A refunded subscription is flagged loudly; voiding its
   enrollments is the admin's action. Completed enrollments and issued
   certificates are immutable 9.02 records a refund cannot unmake —
   that is an accepted sponsor exposure and the changelog says so.
6. The two 018 rules this feature deliberately changes, named as
   reversals in the changelog: "the webhook is the sole creator of
   enrollments" (a subscriber's enroll is a click) and "the refund
   policy covers course sales" (it now also covers subscriptions).

## Read before building

- 018 end to end: `services/stripe_gateway.py`, `services/payments.py`,
  the webhook router, the idempotency table, `livemode` stamping (026),
  and the config/open-gate rules. Extend the boundary module; do not
  write a second Stripe client.
- 028: `enroll` sources and CHECK, renewal eligibility derivation, the
  "already purchased → renew" checkout refusal. Subscription plugs into
  both at the one-line places 028's changelog named.
- 025's `SiteHeader` render rule (`siteFace()`), for the Subscribe link.
- 011's policies: registration (item 8) and refund (item 9) gain new
  operator-published versions. Code links them, never restates them.
- House rules: money in integer cents; Stripe-reported facts recorded,
  never re-derived; financial rows never deleted; derived state.

## Locators — read these in the 2026 Standards PDF before writing code

Printed page numbers in
`docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`.

- **9.02.2(3)** (page 24): the expiration date is "no longer than one
  year from the date of purchase or enrollment" for individual courses.
  A subscription is not an enrollment; each course enrolled under it
  carries its own one-year date from enrollment. Nothing here creates a
  multi-course enrollment or extends any date.
- **8.01** items 8 and 9 (page 20): registration requirements, and the
  "refund policy for courses sold for a fee or cancellation policy". A
  subscription is a fee; the refund and cancellation policy must cover
  it. **8.01.1** (page 21): policies "formalized, published, and made
  available" — the subscribe page links them.
- **9.02** (page 22): retain documentation five years. Subscription and
  invoice rows are financial records, retained like `payments`,
  outliving `RETENTION_YEARS`. A lapse deletes nothing; that is what
  "all my data is still there" rests on.

## In scope

### 1. Task 0 — establish, then decide scope

Answer each in the changelog before writing code:

1. Does the gateway's `create_checkout_session` accept a mode, and
   does the `stripe` package version in requirements support Checkout
   `subscription` mode with `payment_method_collection="always"` and
   `discounts=[{"coupon": ...}]`? Name the version.
2. Does an account already carry a `stripe_customer_id`, or did 018
   create a guest customer per Checkout? Billing needs one durable
   customer per account so a re-subscribe reuses it and the portal
   works. If 018 created guests, say so; this feature adds the column
   and creates the customer on first subscription checkout, never
   backfilling guests.
3. Which webhook event types does `handle_event` dispatch on today,
   and how are unhandled types logged? List the new types and confirm
   each is idempotent by event id through the existing table.
4. How does 028 derive renewal eligibility ("paid payment row for the
   course")? Identify the single line where "or a prior
   subscription-sourced enrollment" joins it.
5. Does the restricted key from 026's OPERATIONS section have the
   scopes Billing needs (Customers write, Subscriptions read,
   Coupons write, Billing Portal sessions write, Invoices read)? Report
   which are missing so the operator adds them; do not widen anything
   in code.
6. Where does the course page render the enroll/price section (018,
   revised by 028)? It gains the second option.

### 2. Constants and config

- `backend/app/constants/subscription.py`:
  `SUBSCRIPTION_PRICE_CENTS = 14900` ("ours"),
  `SUBSCRIPTION_PERIOD_DAYS = 365` ("ours"; Stripe's yearly interval is
  the schedule; this is for display and tests). The display price
  renders from the constant; the charged amount is whatever Stripe's
  Price object says.
- `STRIPE_SUBSCRIPTION_PRICE_ID` joins 012's config validation as part
  of the all-or-nothing Stripe group. The operator creates the Product
  and yearly Price in the dashboard (OPERATIONS.md step) and the
  runbook says the Price amount must equal the constant. Preflight
  compares the two by one `Price.retrieve` when the site is open and
  refuses on mismatch, naming both numbers; while coming-soon it is a
  note. (Same shape as 026's live-key check.)

### 3. Data model

- `accounts.stripe_customer_id` nullable, unique. Set once.
- `subscriptions`: id, account_id (FK RESTRICT), stripe_subscription_id
  (unique), stripe_checkout_session_id (nullable, unique),
  status (as Stripe reports it: `incomplete`, `incomplete_expired`,
  `active`, `past_due`, `canceled`, `unpaid` — CHECK by hand),
  current_period_start, current_period_end, cancel_at_period_end
  (bool), canceled_at (nullable), credit_applied_cents (int, the
  discount Stripe reported on the first invoice, not the number we
  computed), livemode (nullable bool, 026's rule), created_at,
  updated_at. Docstring: financial record, never deleted, outlives
  `RETENTION_YEARS`.
- `subscription_invoices`: id, subscription_id (FK), stripe_invoice_id
  (unique), amount_paid_cents, currency, status (`paid`, `open`,
  `void`, `uncollectible`, `refunded`), period_start, period_end,
  livemode, created_at. One row per Stripe invoice; the renewal paper
  trail. Same docstring.
- `payments.credited_to_subscription_id` nullable FK: set when a
  course payment's amount is applied as credit, so it is never credited
  twice. This is a stored fact about a financial event, not derived
  state — the credit was applied on a specific invoice.
- `enrollments.source` CHECK gains `subscription` (hand-written
  migration, as 028 did).

### 4. Entitlement and enrollment

- `services/subscriptions.py`: `current(db, account) -> Subscription |
  None` — the newest subscription with status `active` and
  `current_period_end > now`. `past_due` is **not** current: Stripe
  retries the card on its schedule and the participant sees a "payment
  failed, update your card" state (section 7) until `invoice.paid`
  lands. Say this in the docstring; it is the one place grace is
  decided, and it is decided as none.
- `POST /api/v1/courses/{code}/enroll` — logged-in participant with a
  current subscription; course published; no active or completed
  enrollment for the course (an expired one is fine: this is the
  subscriber's renewal path and takes precedence over 028's route,
  which stays for non-subscribers). Calls the one constructor with
  `source="subscription"`, one-year clock. 422 per failed condition.
- 028's renewal eligibility gains "or any prior `subscription`-sourced
  enrollment for the course" as the second qualifying condition, at
  the line Task 0.4 identified. A lapsed subscriber who started a
  course under the subscription and let it expire renews it free, as
  a purchaser would.
- 018's checkout is refused for a participant with a current
  subscription ("your subscription covers this course; enroll
  directly"), one more line in the refusal matrix.

### 5. Subscribing, credit, and the coupon

- `POST /api/v1/subscribe` — logged-in, verified participant, no
  current subscription and no `incomplete` subscription younger than
  the Checkout session lifetime (return that session's URL instead).
  Steps, in one service function:
  1. Ensure `stripe_customer_id` (create the Customer with the
     account's email and id in metadata; store it).
  2. Compute credit: sum of `amount_cents` over the account's payments
     with status `paid` and `credited_to_subscription_id IS NULL`,
     capped at `SUBSCRIPTION_PRICE_CENTS`. Zero is a valid result and
     skips the coupon.
  3. If credit > 0: create a single-use, `duration="once"`,
     `amount_off` coupon in the subscription's currency, with the
     account id and the credited payment ids in metadata. (Per-customer
     coupons are the honest shape: no shared promo code, no reuse.)
  4. Create the Checkout Session: `mode="subscription"`, the configured
     Price, `customer` set, `payment_method_collection="always"`,
     `discounts=[{"coupon": id}]` when credited, `metadata` carrying
     account id and the credited payment ids, success URL
     `/subscribe/success?session_id=…`, cancel URL `/subscribe`.
  5. Write the `subscriptions` row as `incomplete` with the session id
     and `livemode` from the session **before** returning the URL
     (018's ordering). `credit_applied_cents` stays 0 until Stripe
     reports the discount on the first invoice.
- Credit is marked as consumed (`credited_to_subscription_id`) **only
  when the webhook confirms the first invoice was paid with that
  discount** — never at session creation, or an abandoned session
  would burn the credit. Two abandoned sessions in a row leave the
  credit intact; the test proves it.
- The credit is a one-time event per account by construction: after
  it is consumed the payments carry the FK and the sum is zero. A
  second subscription (after a lapse) gets credit only for course
  purchases made in between, which under 018's new refusal cannot
  happen while subscribed — so in practice, only purchases made while
  lapsed.

### 6. Webhook

Extend `handle_event`, idempotent by event id as 018:

- `checkout.session.completed` with `mode == "subscription"`: find the
  `subscriptions` row by session id; set `stripe_subscription_id`,
  status, period, `livemode` re-stamped from the object. If the
  session's `total_details.amount_discount` > 0, that is
  `credit_applied_cents`, and the payment ids from metadata get their
  FK set — one transaction. A session id with no row logs loudly and
  answers 200 (018's orphan rule).
- `customer.subscription.updated` / `.deleted`: sync status, period,
  `cancel_at_period_end`, `canceled_at` from the object. Never infer;
  copy.
- `invoice.paid`: upsert `subscription_invoices` from the invoice;
  sync the subscription's period from the invoice lines. This is the
  renewal event.
- `invoice.payment_failed`: upsert the invoice row as `open`; the
  subscription's status follows the next `customer.subscription.updated`
  (Stripe moves it to `past_due` itself). No email of our own: Stripe's
  dunning emails are enabled in the dashboard (OPERATIONS step), the
  same posture as 018's receipt email.
- `charge.refunded` on a subscription invoice: mark the invoice row
  `refunded` and **stop** — no status change, no voiding. The admin
  subscriptions view flags refunded-with-current-subscription and
  refunded-with-active-enrollments loudly. Cancelling the subscription
  in Stripe is a separate act the admin performs in the dashboard as
  part of the refund runbook; the webhook then syncs the status.
- Unhandled types: 200 and logged by name, as today.

### 7. Participant surface

- `/subscribe`: the offer — price from the constant, "unlimited course
  enrollments for one year, renews automatically, cancel any time",
  the credit line when > 0 ("Your $58 in course purchases is credited:
  you pay $91 today"), links to the registration and refund policies,
  and the Subscribe button (→ Stripe). Signed-out visitors see the
  page at `open` with Sign in / Create account instead of the button.
  Everything on it is 8.01 disclosure about the *subscription*, not a
  course; no course fact appears.
- `/subscribe/success`: polls `GET /api/v1/subscribe/{session_id}/status`
  (owner-only, 018's pattern) until the webhook lands, then links to
  the catalog. Same ~30s honest-delay state.
- `/account` gains a Subscription section: current / renews on date /
  cancels on date / past due (with "Update payment method") / none,
  the credit consumed, and a **Manage subscription** button that
  creates a Stripe Customer Portal session and redirects
  (`POST /api/v1/subscribe/portal`). Cancellation, card update, and
  invoice history live in the portal; superCPE builds none of them.
  The portal configuration (what it allows) is an OPERATIONS step.
- Site header (025): for a signed-in participant without a current
  subscription, one link, "Subscribe", to `/subscribe`. Under the
  header's existing render rule — null while coming-soon, null under
  `/admin`. For signed-out visitors, nothing changes in the header;
  the offer is reachable from the course page and the footer.
- Course page enroll section: for a signed-in non-subscriber, two
  choices side by side — "Buy this course $29" (018) and "Subscribe
  $149/yr — unlimited courses" (→ `/subscribe`), the credit line under
  the second when > 0. For a current subscriber: "Enroll (included in
  your subscription)". For a lapsed subscriber: the two choices again,
  plus 028's free-renewal button on courses they started. `/my/courses`
  cards follow 027's next-step derivation; a subscriber's next step on
  an expired started course is "Enroll again (included)".
- Footer (027): a "Subscribe" link.

### 8. Admin

- `/admin/subscriptions`: table (account, status, period, credit,
  cancel-at-period-end, Stripe link honoring `livemode`), the two loud
  flags from section 6, and the invoices per subscription. No actions
  beyond the existing enrollment void (018), which now also lists a
  refunded subscription's active enrollments.
- `/admin/payments` shows the credited-to-subscription marker on
  course payments that were consumed.

### 9. Config, gate, ops

- `STRIPE_SUBSCRIPTION_PRICE_ID` in the all-or-nothing Stripe group;
  the open gate's `payments_not_configured` covers it. Preflight price
  check per section 2.
- OPERATIONS.md "Subscriptions (029)": create Product and yearly Price,
  set the env var, restricted-key scopes added (from Task 0.5),
  register the four new event types on **both** webhook endpoints,
  configure the Customer Portal (cancel at period end allowed, card
  update allowed, plan switching off), enable Stripe dunning emails,
  Stripe CLI test-mode walkthrough (subscribe with and without credit,
  renew via `stripe trigger invoice.paid`, cancel via portal, refund),
  and the refund runbook: refund the invoice in Stripe, cancel the
  subscription in Stripe, watch both flags, void enrollments per the
  policy. Note that Stripe Tax applies to subscriptions the same way
  the 018 ROADMAP note describes.

### 10. Policy text (operator, not code)

Two new policy versions, wording drafted by the build session under
Decisions, published by the operator through the 011 admin path:

- Registration (item 8): the subscription — one year from purchase,
  renews automatically, unlimited enrollments while current, each
  enrollment's own one-year expiration, lapse retains all records,
  prior course purchases credited once against the first payment.
- Refund and cancellation (item 9): full refund of the current
  subscription payment on request, no pro-rata, no questions; cancel
  any time and access continues to the period end; what happens to
  enrollments and issued certificates after a refund (per section 1
  item 5 — certificates and completed credit stand; access to
  in-progress enrollments ends).

## Out of scope (report, do not build)

- Monthly or other intervals; team or multi-seat plans; gifting.
- Plan switching, trials, promo codes, coupons other than the
  per-account credit coupon.
- Automatic voiding on refund (018's decision stands); automatic
  cancellation on refund (admin does it in Stripe).
- Any email of superCPE's own about billing (Stripe's receipts and
  dunning).
- Grace periods for `past_due` (decided: none; recorded).
- Google sign-in (030).

## Tests

Backend (baseline 481), all through the stubbed gateway:

- Entitlement: `active` + period ahead → current; `active` + period
  behind, `past_due`, `canceled`, `incomplete` → not current.
- Enroll: subscriber on a published course → one `subscription`
  enrollment, one-year expiry, no Stripe call; refused for
  non-subscriber, unpublished, active/completed existing; expired
  existing → allowed (subscriber renewal); second call refused.
- Checkout refused for a current subscriber; 028 renewal eligible via
  a prior subscription enrollment after lapse.
- Subscribe: customer created once and reused; credit computed from
  `paid` uncredited payments only, refunded excluded, capped; zero
  credit → no coupon; row written `incomplete` before URL returned;
  live incomplete session reused, not duplicated.
- Credit consumption: abandoned session leaves payments uncredited;
  completed session with discount sets `credit_applied_cents` from
  the object and the FKs in one transaction; replayed event changes
  nothing; a second subscribe after that computes zero credit.
- Webhook matrix: each new type idempotent by event id; status and
  period copied, never inferred; orphan session id logs and answers
  200; refund marks the invoice and touches nothing else; unhandled
  types 200.
- Preflight: price mismatch refuses open naming both amounts; match
  passes; coming-soon is a note.
- Router walk green; every new route 404s anonymously in
  `coming_soon`; `INTENTIONALLY_PUBLIC` untouched (the existing
  webhook exemption covers the new event types). No response on any
  new route carries a course fact or "National Registry".
- Migration: `source` CHECK accepts `subscription`; the `status` CHECK
  rejects an unknown value.

Frontend (baseline 82):

- Header shows Subscribe for a non-subscribing participant at open,
  not for a subscriber, not in coming-soon, not under `/admin`.
- Course page renders the two-choice section, the included-enroll
  button, and the credit line from mocked payloads.
- `/subscribe` renders price from payload, credit line only when > 0,
  policy links present; `/account` states for each status; success
  page polls and lands.

## COMPLIANCE.md rows

- 9.02.2(3): append — subscription-sourced enrollments carry the same
  one-year expiration from enrollment; a subscription's own period is
  not an enrollment date and extends nothing.
- 8.01 items 8 and 9: append — the subscription is disclosed on
  `/subscribe` with price, term, renewal, and links to both policies;
  the operator-published versions cover subscriptions (dated at
  acceptance).
- 9.02: append — `subscriptions`, `subscription_invoices`, and the
  credit FK on `payments` are financial records retained beyond
  `RETENTION_YEARS`; a lapse deletes nothing.
- 018's 9.02 payment row: append — amounts and discounts recorded as
  Stripe reported them.

## Acceptance

1. Local, stubbed: a participant with two $29 paid courses opens
   `/subscribe`, sees "$58 credited, $91 today"; the stubbed session
   completes; the subscription is current, `credit_applied_cents` is
   5800, both payments carry the FK; `/account` shows the renewal
   date.
2. Local: the subscriber enrolls in `ATO` with no Stripe call; the
   enrollment expires one year out; checkout for another course is
   refused as covered.
3. Local: simulate `customer.subscription.deleted`; entitlement ends;
   the `ATO` enrollment is untouched and still active; set it expired;
   028's renewal button appears and works.
4. Local: simulate a refund on the first invoice; the invoice is
   `refunded`, both admin flags show, nothing is voided; void from the
   existing action; flags clear.
5. Preflight refuses on a mismatched price, passes on a match; open
   gate refuses without the price id.
6. pyflakes, oxlint, both suites green; router walk green, allowlist
   untouched.
7. Operator: Stripe test-mode walkthrough per OPERATIONS.md with the
   CLI — subscribe with credit, renew, cancel via portal, refund —
   logged in the table.
8. Operator: publish both policy versions.
9. Operator: deploy with the sha from `git rev-parse --short
   origin/main`; repeat 1 and 2 on production in Stripe test mode (the
   site is still coming-soon; keys are test until opening day per 026).

## When done

Per CLAUDE.md rule 5: 7–9 are the operator's; stop and report when
1–6 pass with the changelog draft carrying the Task 0 answers, the two
018 reversals named, the drafted policy wording for both kinds, the
restricted-key scopes the operator must add, and the accepted exposure
that completed credit survives a refund. Append only.
