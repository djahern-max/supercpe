# Feature 028 — Unlimited re-takes and free renewal after expiry

Policy feature from the 2026-09-12 walkthrough finding W5 (the
exhausted-retakes dead end) and the sponsor decision recorded 2026-09-12:
**a participant who has paid for a course never pays for it again**, and
**re-takes of the qualified assessment are not limited.** Both are
sponsor policy choices the Standards leave open. Neither loosens the
one-year expiration, which the Standards fix.

## What this feature decides

1. `RETAKES_ALLOWED` becomes unlimited. The exhausted state 027 gave
   honest wording to becomes unreachable under the platform's policy;
   the code path stays for any future finite policy.
2. An enrollment still expires one year from enrollment (9.02.2(3),
   unchanged). After expiry, a participant who paid and did not
   complete may start a **new enrollment at no charge** — a fresh year,
   no Stripe call. The expired enrollment and every attempt on it are
   retained; the study guide on it stays readable as 010 already
   allows.
3. 018's "re-purchase after expiry" path is narrowed: checkout is for a
   first purchase of a course only. Anyone with a paid payment row for
   the course renews instead. This is a deliberate narrowing of a
   recorded 018 decision; the changelog names it as such.

## Read before building

- 010's enrollment constructor (`enrollments_service.enroll`, the one
  constructor), `status`, `progress`, `retakes_remaining`, and
  `ENROLLMENT_DAYS`. 018's `_active_enrollment`, `start_checkout`, and
  the `source` values the constructor accepts (`purchase`, and whatever
  else exists — Task 0).
- `policies.retake_policy_text()`: the policy page renders this
  sentence from the constants so it cannot disagree with the code. It
  must keep that property after this feature.
- 027's `RetakesExhausted.jsx` and `nextStep.js`: do not delete the
  exhausted branch; make it conditional on a finite policy.
- The house rule: derived state, never stored booleans. "Eligible to
  renew" is derived from payment and enrollment rows; nothing is
  written except the new enrollment.

## Locators — read these in the 2026 Standards PDF before writing code

Printed page numbers in
`docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`.

- **6.01.2** (page 13): "The number of re-takes a participant is
  permitted to take is at the sponsor's discretion." Unlimited is a
  permitted choice. (page 14) On a failed assessment no feedback may be
  given — unchanged and untouched.
- **9.02.2(3)** (page 24): course documentation "must include an
  expiration date (the time by which the participant must complete the
  qualified assessment). For individual courses, the expiration date is
  no longer than one year from the date of purchase or enrollment."
  This feature does not extend any expiration; a renewal is a new
  enrollment with its own date, which the paragraph permits because
  the year runs "from the date of … enrollment".
- **8.01** items 8 and 9 (page 20): "Course registration and, where
  applicable, attendance requirements" and "Refund policy for courses
  sold for a fee". The registration policy must state the renewal
  rule; the refund policy is unchanged.
- **8.01.1** (page 20): registration policies must be "formalized,
  published, and made available". The rule lives in the published
  policy, linked, not restated on every page.

## In scope

### 1. Task 0 — establish, then decide scope

Answer each in the changelog before writing code:

1. What `source` values does `enrollments_service.enroll` accept
   today, and is the value constrained by a CHECK? (A new value needs
   the constraint updated by hand.)
2. Where is `retakes_remaining` consumed — backend refusals, the
   result payload, the course-page payload, 027's frontend — so every
   consumer handles `None`?
3. Does any test assert the exhausted refusal message or `RETAKES_ALLOWED`
   as an integer? List them; they become "finite policy" tests.
4. What does 018 do today when an *expired* participant calls
   checkout: does it create a second Stripe session and a second
   payment row? Confirm before narrowing it.
5. Is the current registration/attendance policy version's text in the
   database only, or is there a seed or fixture? The renewal sentence
   is a new policy version the operator writes, not code (policies are
   append-only versions, 011) — confirm the admin path for adding one
   and whether the test factory needs a policy that mentions renewal.

### 2. Unlimited re-takes

- `RETAKES_ALLOWED: int | None = None` in
  `backend/app/constants/assessment.py`. Rewrite the comment: 6.01.2
  leaves the count to the sponsor; `None` is unlimited; an integer is
  re-takes after the first sitting per enrollment; every attempt is
  retained whatever the value; 011's policy text renders whichever it
  is.
- `enrollments_service.retakes_remaining` returns `None` when the
  policy is unlimited. `assessment.start_for_enrollment` skips the
  sittings check when it is `None`. All other refusals (completed,
  expired, voided, unanswered review questions, open attempt) are
  unchanged.
- `assessment.result` and the course-page/progress payloads carry
  `retakes_remaining` as nullable; `retakes_unlimited: bool` beside it
  if the frontend is cleaner with it (say which in the changelog).
- `policies.retake_policy_text()` renders: with `None`, "A cumulative
  grade of at least {PASSING_PCT} percent … is required to pass. A
  participant may re-take the qualified assessment as many times as
  needed. Every sitting must be completed before the enrollment
  expires, {ENROLLMENT_DAYS} days after enrollment." With an integer,
  the existing sentence. Both branches tested.
- Frontend: 027's failed-result page shows the score, the threshold,
  and "Re-take the assessment" when unlimited — no count. The
  `RetakesExhausted` notice renders only when `retakes_remaining` is
  `0`, which cannot occur under the shipped policy; a test pins that it
  still renders under a finite mock so the path is not dead code by
  accident.

### 3. Free renewal after expiry

- Derived eligibility, in `enrollments_service` (or `payments`, whichever
  owns the payment lookup): a participant may renew a course when they
  hold at least one `paid` payment row for it (018's rows; a refunded
  payment does not qualify), have **no active or completed** enrollment
  for it, and their most recent enrollment for it is `expired`. A voided
  enrollment does not qualify (the money came back). A subscription
  source, when 029 exists, will be a second qualifying condition; leave
  a one-line comment naming that, build nothing for it.
- `POST /api/v1/courses/{code}/renew` — logged-in participant, course
  published. Refuses with a distinct 422 error for each failed
  condition (no paid purchase; enrollment still active; already
  completed; enrollment voided). On success, calls the one constructor
  with `source="renewal"`; one-year clock from now; returns the new
  enrollment. Idempotency: a second call while the new enrollment is
  active is refused by the active-enrollment condition, so no
  duplicate.
- The renewed enrollment starts with **no review questions answered
  and no attempts**. 010 pins packages at enrollment: a renewal pins
  the course's *current* published packages, not the expired
  enrollment's. If the course was re-reviewed and republished in the
  interim the participant reads the current guide; that is correct and
  the changelog says so.
- 018 narrowing: `start_checkout` refuses when the participant already
  holds a `paid` payment for the course, with the message "you have
  already purchased this course; renew it from the course page instead
  of paying again." The existing pending-session reuse and
  active-enrollment refusals stay. The 018 test "re-purchase allowed
  after expiry" is rewritten to "renewal after expiry, checkout
  refused" and the changelog names the reversal.
- Course page, `/my/courses` card, and 027's next-step derivation: an
  expired enrollment with renewal eligibility shows a primary "Start a
  new enrollment (no charge)" button; on success, land on the course
  page in the enrolled state. An expired enrollment *without*
  eligibility (never paid — a goodwill or admin-created enrollment
  from 010's CLI, say) shows the Enroll/price button as today.
- Admin: the enrollments list shows `source` (it may already);
  `renewal` rows visible. No admin action added.

### 4. Policy text (operator, not code)

The registration/attendance policy gains a new version stating, in
substance: an enrollment expires one year from enrollment; a
participant who purchased a course and did not complete it may start a
new one-year enrollment at no additional charge; re-takes of the
qualified assessment are unlimited within the enrollment period. The
build session drafts the wording in the changelog under Decisions; the
operator publishes it as a new policy version through the existing
admin path (011). Publishing the policy is acceptance item 6 and the
operator's.

## Out of scope (report, do not build)

- Per-course retake limits or per-course policy text (decision
  recorded 2026-09-12: one platform policy).
- Extending an existing enrollment's `expires_at` (9.02.2(3) is a cap;
  010's decision stands).
- Renewal of a *completed* enrollment (nothing to renew; a certificate
  is permanent and a course cannot be re-taken for credit on the same
  enrollment).
- Subscriptions (029) — but name in the changelog where a subscription
  source would plug into the eligibility derivation.
- Any change to refund handling, voiding, or the refund policy.
- Deleting or rewriting 027's exhausted wording.

## Locators — code

Find by grep and record actual paths:

- `backend/app/constants/assessment.py`, `constants/enrollment.py`
- `backend/app/services/enrollments.py` (`enroll`, `status`,
  `progress`, `retakes_remaining`), `services/assessment.py`
  (`start_for_enrollment`, `result`), `services/payments.py`
  (`start_checkout`, `_active_enrollment`), `services/policies.py`
  (`retake_policy_text`)
- `backend/app/routers/` — the course/enrollment router for the new
  route; `schemas/` for the nullable `retakes_remaining`
- `backend/app/models/enrollment.py` — the `source` CHECK
- Frontend: `MyAssessment` result, `MyCourse`, `MyCourses`,
  `nextStep.js`, `RetakesExhausted.jsx`, course page enroll section

## Data model

- `enrollments.source` CHECK gains `renewal`. Migration by hand (the
  CHECK is not autogenerated). No other schema change. No FK from the
  renewal to the payment or the expired enrollment — derived, per the
  house rule; the changelog restates it.

## Tests

Backend (baseline 465):

- `RETAKES_ALLOWED = None`: after any number of failures, start is
  permitted; `retakes_remaining` is `None`; result payload nullable;
  policy text renders the unlimited sentence. Under a monkeypatched
  integer: the existing sittings refusal and count behavior still hold
  (the finite tests from Task 0.3, kept and renamed).
- Renewal eligibility matrix: paid + expired → allowed, one new
  `renewal` enrollment with a one-year `expires_at`, no attempts, no
  answers, packages pinned to current; paid + active → refused; paid +
  completed → refused; refunded + expired → refused; voided → refused;
  never paid + expired → refused; unpublished course → refused; second
  call while active → refused (no duplicate).
- Checkout refuses a participant with a prior `paid` payment for the
  course; still allows a first purchase; pending-session reuse
  unchanged. The 018 expired-repurchase test rewritten as above.
- Expired enrollment's read access and attempt history unchanged after
  renewal (retention).
- Router walk green; `/renew` 404s anonymously in `coming_soon` like
  every participant route; nothing added to `INTENTIONALLY_PUBLIC`.

Frontend (baseline 73):

- Failed result under unlimited shows Re-take and no count; under a
  finite mock with 0 remaining still renders `RetakesExhausted`.
- Course page and `/my/courses` show the renewal button only when the
  payload says eligible; clicking it calls `/renew` and re-renders
  enrolled.

## COMPLIANCE.md rows

- 6.01.2 (re-takes): update the row — `RETAKES_ALLOWED` is `None`
  (unlimited) by sponsor policy; every attempt retained; policy text
  derived; finite policy remains supported.
- 9.02.2(3): append — renewal creates a new enrollment with its own
  one-year expiration; no `expires_at` is ever extended; the expired
  enrollment and its attempts are retained.
- 8.01 item 8: append — the published registration policy states the
  renewal and re-take rules (operator-published version, date noted
  once acceptance 6 passes).
- 8.01 item 9: append — unchanged; a renewal is not a sale and creates
  no payment row.

## Acceptance

1. Local: enroll a participant in `ATO`, fail the assessment five
   times; each result offers Re-take with no count; `/policies` shows
   the unlimited sentence.
2. Local: set the enrollment's `expires_at` into the past (dev shell);
   the course page shows "Start a new enrollment (no charge)"; clicking
   creates a `renewal` enrollment with a fresh year, no answers, no
   attempts; the old enrollment's study guide still opens read-only
   and its attempts are in the admin history.
3. Local: with the stubbed Stripe boundary, checkout for that course
   is refused with the already-purchased message; a first purchase of
   a different course still returns a session.
4. Local: a refunded-then-voided enrollment, expired, shows no renewal
   button and checkout is allowed (never paid successfully, in
   effect).
5. Typecheck, lint, backend and frontend suites green; router walk
   green with the allowlist untouched.
6. Operator: publish the new registration/attendance policy version
   from the drafted wording; `/policies` shows it.
7. Operator: deploy with the sha from `git rev-parse --short
   origin/main`; repeat 1 and 2 on production as the test participant.

## When done

Per CLAUDE.md rule 5: acceptance 6 and 7 are the operator's; stop and
report when 1–5 pass, with the changelog draft including the Task 0
answers, the 018 narrowing named as a reversal, the drafted policy
wording, and the one-line note on where a 029 subscription source
plugs into renewal eligibility. Strike the "028 — exhausted
enrollments" ROADMAP note 027 added and replace it with this feature's
line. Append only.
