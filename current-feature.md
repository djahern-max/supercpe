# Current Feature

## Feature 008, Development and review chain, and the publish gate

## Goal
Every course names the subject matter expert who developed it and a
different one who reviewed it, with the review dated against the content it
reviewed. A course publishes only when the readiness checklist has no block
findings, a qualifying review exists, and the required licensed CPA took
part. A published course is immutable; changing it means unpublishing,
editing, and reviewing again. The most recent review date is disclosed
where 4.01 requires it.

## In scope
- `subject_matter_experts`, deliberately not tied to accounts
- Developer on the course; dated review records with a decision
- The licensed-CPA participation rule for Accounting, Auditing, Taxes
- The publish gate, and publish/unpublish
- Immutability of published courses
- Review cycle (annual / biennial) stored; due date derived
- Public disclosure of developer, reviewer, review date

## Out of scope
- Overdue-review reporting and reminders (011 reports; nothing reminds).
- An approval workflow with queues and notifications. A review is a
  recorded fact, entered by an admin on the reviewer's behalf or by the
  reviewer if 009 later gives them a login.
- Instructor rules (4.03). Self study has no instructor.
- Evaluations (4.04). 011.
- Verifying a license against a state board. Recorded, not verified; say
  so in COMPLIANCE.

## Locators
Read 4.01, 4.01.1, 4.02, 4.02.1, and 9.02.2(4) before writing code, and
take Requirement text from the PDF. The rules that shape this feature:

- 4.01: course documentation must contain the most recent publication,
  revision, or review date. Subjects that change frequently: reviewed at
  least yearly; others at least every two years.
- 4.01.1: developed by a subject matter expert; **when technology is used
  in development, the content developer is responsible for reviewing the
  content for accuracy.** superCPE's content is drafted with a language
  model in video-tool from authoritative sources; the developer of record
  is the human who directed and checked that draft. The SME record must be
  able to say so.
- 4.02: reviewed by content reviewers **other than those who developed the
  program**, before first presentation and after each significant
  revision. At least one licensed CPA (active, good standing, U.S.
  jurisdiction) must participate in developing every Accounting or
  Auditing program; a CPA, tax attorney, or enrolled agent for Taxes.
  Either role satisfies it.
- 4.02.1: reviewers qualified in the subject matter. Where advance review
  was impractical, the basis must be documented — model this as a field,
  not as a bypass.
- 9.02.2(4): retain the reviewer's name, credentials, and the review.

## Data model
Table `subject_matter_experts`:
- id, name, credentials (free text, e.g. "CPA"), credential_type (CHECK in
  cpa / tax_attorney / enrolled_agent / other), license_jurisdiction,
  license_number, license_status (CHECK in active / inactive / unknown),
  email (optional), notes, created_at, updated_at
- No FK to any accounts table, now or in 009. An SME is a person who was
  qualified on a date; an account is a login. Different lifetimes.

On `courses`:
- developer_id (FK sme, nullable), developer_used_technology (bool, not
  null, default true — the 4.01.1 fact; default reflects how superCPE
  content is made), review_cycle (CHECK in annual / biennial, default
  biennial), published_at (nullable), unpublished_at (nullable)

Table `course_reviews`:
- id, course_id (FK), reviewer_id (FK sme), reviewed_at (date),
  content_updated_at_reviewed (timestamp: the course's `content_updated_at`
  at the moment the review was recorded — the review is of *that* content),
  decision (CHECK in approved / changes_requested), notes (text),
  impractical_basis (text, nullable — 4.02.1's rare case; if set, decision
  may be approved without the reviewer having read... no. Keep it simpler:
  this field documents why review before first presentation was
  impractical, and its presence is reported, never used to bypass anything),
  recorded_by (string; the admin identity available today), created_at

A review is immutable once recorded. Corrections are new reviews.

## Derived
- `current_review(course)`: latest review with `decision == approved` whose
  `content_updated_at_reviewed >= course.content_updated_at`. None if the
  content has changed since.
- `review_due_at(course)`: `current_review.reviewed_at + 365 or 730 days`.
- `last_documented_date(course)`: the greater of `published_at` and the
  latest review's `reviewed_at`; this is the 4.01 disclosure.

## Readiness findings (extend `readiness.check`)
- `developer_missing` (block)
- `review_missing` (block) — no approved review of the current content;
  message says whether none exists or the content changed since (with both
  timestamps)
- `reviewer_is_developer` (block) — the current review's reviewer is the
  developer. 4.02 is explicit.
- `cpa_participation` (block) — field of study is Accounting, Auditing, or
  Taxes and neither developer nor reviewer has `credential_type == cpa`
  (for Taxes, also accept tax_attorney or enrolled_agent) with
  `license_status == active`. Name the field and the rule.
- `description_missing` (block) — the 8.01 announcement text is blank
- `review_due` (warn) — `review_due_at` is past; block findings only
  arise from content and review facts, so an overdue course can still be
  unpublished and republished after a fresh review, which is the fix

## Publish
`POST /admin/courses/{code}/publish`: runs `readiness.check`; refuses with
every block finding at once as 422 (same shape); on success sets `status =
published`, `published_at = now()`. `POST …/unpublish` sets draft,
`unpublished_at`. Both call nothing that touches content, so
`content_updated_at` is unchanged and the review stays current.

**Immutability:** every `courses` service mutation that calls `touch`
(attach, detach, move, update-version, title and description edits)
refuses with a 422 naming the rule when `status == published`. The message
says to unpublish first. Setting the developer or recording a review is
not a content change and is allowed on a published course; it cannot make
readiness worse. Test that a published course with a new review recorded
stays published and its disclosure date advances.

Sponsor `missing_fields` does **not** gate publish. Publish makes a course
visible; the sponsor's registry status gates certificates (010).

## Endpoints
- Admin CRUD `/admin/smes`
- `PUT /admin/courses/{code}/developer` `{sme_id, used_technology}`
- `POST /admin/courses/{code}/reviews`, `GET …/reviews`
- `PUT /admin/courses/{code}/review-cycle`
- publish / unpublish
- Public course payload gains: `developed_by` (name, credentials),
  `reviewed_by` (name, credentials), `last_reviewed` (date),
  `last_documented_date`. Never license numbers publicly.

## UI
- `/admin/smes`: list and edit form. Credential type and license status
  as selects. A note under the form that license claims are recorded as
  stated and superCPE does not verify them.
- `/admin/courses/:code`: a Development & Review card above Readiness:
  developer (select from SMEs, technology checkbox with the 4.01.1 sentence
  beside it), review cycle, the review history (reviewer, date, decision,
  notes, and whether it is the current review or superseded by a content
  change), a "Record review" form (reviewer, date, decision, notes,
  impractical basis collapsed under a link). Publish / Unpublish button
  with the readiness state beside it; when refused, the block findings
  listed. On a published course, every content control is disabled with
  the immutability note.
- `/courses/:code` public page: after the disclosure list, a short
  provenance block: "Developed by … CPA. Reviewed by … CPA on 12 Sep 2026."
  and the last documented date.

## Tests
- SME CRUD; an SME cannot be deleted while named on any course or review
- publish refuses with all block findings at once; a course with
  developer, distinct approved reviewer, active CPA, description, fresh
  credit, and enough questions publishes
- reviewer == developer refuses
- Accounting course with a non-CPA developer and non-CPA reviewer refuses;
  making either an active CPA passes; a Taxes course accepts an enrolled
  agent
- a review recorded, then a content change, then publish → refused as
  stale, message shows both timestamps; a new review → publishes
- every `touch` path refuses on a published course; unpublish, edit,
  re-review, publish works end to end
- recording a review on a published course does not unpublish it and
  advances the disclosure date
- public payload shows names and credentials, never license numbers
- `review_due_at`: annual vs biennial

## COMPLIANCE.md
Rows for 4.01 (dates disclosed; cycle stored; enforcement of currency is
reporting only — Gap), 4.01.1 (developer of record with the technology
flag; credentials recorded not verified — Gap), 4.02 (distinct reviewer;
CPA participation; before first presentation and after revision enforced
by immutability plus the stale-review block), 4.02.1 (qualification is a
recorded judgment; impractical basis documented as a field), 9.02.2(4).

## Acceptance
- `pytest` passes; migration round-trips
- Create yourself as an SME (developer, technology used) and a second SME
  as reviewer; record an approved review on ASC842-PCX; publish succeeds
  only when readiness is clean; `/courses` now lists the course publicly
  with provenance
- Edit the description on the published course → refused; unpublish, edit,
  publish → refused as stale review; record a review; publish → succeeds

## When done
Append the 008 entry. Decisions: SMEs not accounts; published courses
immutable; reviewer must differ from developer; sponsor status does not
gate publish. Known gaps: licenses recorded not verified; overdue review
reported not enforced; no reviewer login. Then stop.
