# 010 — Enrollment, completion record, and certificate

## Goal

Make the enrollment the record everything hangs off (ROADMAP structural
difference 2), verify completion the way 6.01 requires, and issue a
certificate whose every fact is snapshotted at the moment of completion
(structural difference 4). After this feature a participant can be
enrolled by an admin, watch the course, answer the review questions, take
the qualified assessment, and hold a certificate that a later edit to the
course, the sponsor profile, or their own account cannot change.

Payment is not here. 017 will create the enrollment on a successful
charge; nothing downstream of the enrollment row changes when it does.

## In scope

- `enrollments` with the expiration date set at creation (9.02.2(3)).
- Participant progress: review-question answers and furthest-watched
  position per lesson, keyed to the enrollment (replacing 006's "nothing
  is persisted").
- Attempts keyed to the enrollment (replacing 007's `X-Preview-Id` for
  participants; the preview identity survives for admin and reviewer).
- `completions`: one row per passed enrollment, immutable, carrying the
  9.01 certificate snapshot and the awarded credit.
- Certificate rendering (PDF) from the snapshot only; certificate number
  and verification token; the 60-day issuance clock as an admin finding.
- Pinning: an enrollment records the package versions it enrolled on and
  is served those versions until it completes or expires.
- Admin: enroll a participant, list enrollments and completions per
  course, render a certificate PDF from its snapshot, see overdue
  certificates.
- Participant: `/my/courses`, the player and assessment behind their
  enrollment, the result page, the certificate download.
- Course deletion refused while any enrollment exists (008's known gap).

## Out of scope

- Payment, refunds, pricing (017); self-registration (016).
- Certificate delivery by email and the public verification page (018) —
  this feature stores the verification token 018 will look up.
- Program evaluation (4.04) — 011 attaches it to the completion.
- The audit bundle (011); this feature makes sure everything it needs is
  in rows.
- Per-jurisdiction credit rounding (019); the certificate prints the
  course's one-fifth-rounded award.
- Multi-field credit allocation (004 refuses multi-field courses).

## Locators — read these paragraphs before writing code

- **9.02.2(3)** — course documentation must include an expiration date,
  "the time by which the participant must complete the qualified
  assessment," no longer than one year from purchase or enrollment.
- **6.01** — completion verification; "self-certification … alone is not
  sufficient." 007 built the graded attempt; this feature ties it to a
  person and an enrollment.
- **6.01.2** — 70 percent; re-takes "at the sponsor's discretion"; on a
  failed assessment without a test bank, no feedback. All three are 007
  behavior this feature must preserve when re-gating behind enrollment.
- **9.01** — the eleven certificate items and the 60-day delivery
  expectation. Read the list; the snapshot is the list.
- **9.01.1** — for self study, acceptable evidence is "a certificate
  supplied by the CPE program sponsor after satisfactory completion of a
  qualified assessment." The entity named on the certificate awards the
  credit (003's `legal_name`).
- **9.02.2(1)** — completion records "by individual participant, including
  the number of CPE credits earned … and course completion date."
- **7.01** — credit on the 50-minute hour; the time statement (item 10) is
  003's `TIME_STATEMENT`.

## Data model

One migration. CHECKs by hand. Nothing here is ever deleted.

**`enrollments`**
- `id`, `account_id` FK RESTRICT (role must be participant at creation;
  checked in the service, not the DB), `course_id` FK RESTRICT,
  `enrolled_at`, `expires_at` (= `enrolled_at` + `ENROLLMENT_DAYS`,
  computed in the service and stored — it is a fact about the enrollment,
  not derived state), `source` CHECK IN ('admin', 'purchase') — only
  `'admin'` is written here, `created_by_account_id` FK RESTRICT nullable,
  `package_versions` JSONB (`{package_id: version}` at enrollment, the pin).
- Derived, never stored: `status` — `completed` if a completion row
  exists, else `expired` if `now() > expires_at`, else `active`. One
  function in `app/services/enrollments.py`.
- "One active enrollment per (account, course)" cannot be a partial
  index because it depends on `now()`; enforce in the service (refuse a
  second active enrollment, 422 naming the existing one) and add a plain
  index on `(account_id, course_id)`.

**`lesson_progress`**
- `enrollment_id` FK RESTRICT, `package_id` FK RESTRICT,
  `furthest_seconds` (integer), `updated_at`. Unique on
  `(enrollment_id, package_id)`.

**`review_answers`**
- `enrollment_id`, `question_id` FK RESTRICT (no ON DELETE, like
  `attempt_answers`), `choice_id`, `is_correct` (snapshot of the verdict),
  `answered_at`. Unique on `(enrollment_id, question_id)`; a re-answer
  updates the row and `answered_at`. The 5.01.2 engagement record.

**`attempts`** (existing)
- `enrollment_id` gains its FK RESTRICT. CHECK: exactly one of
  `enrollment_id` / the 007 preview identity is set. The partial unique
  index for one open attempt extends to `(enrollment_id)` where status =
  open.

**`completions`**
- `id`, `enrollment_id` FK RESTRICT unique, `attempt_id` FK RESTRICT
  unique, `completed_at` (= the passing attempt's `submitted_at`),
  `credit_awarded` NUMERIC(4,1), `field_of_study`, `certificate_number`
  (text, unique; `YYYY-NNNNNN` from a per-year sequence), `verification_token`
  (32 random bytes hex, unique; 018 uses it), `certificate_snapshot` JSONB,
  `certificate_key` (storage key of the first rendered PDF, nullable until
  rendered), `certificate_rendered_at` nullable.
- No update path except `certificate_key`/`certificate_rendered_at`
  being set once. No delete path.

**`certificate_snapshot`** — the 9.01 list, item by item, frozen:
```
{
  "sponsor_name": …,            # 1
  "sponsor_legal_name": …,      # 9.01.1
  "participant_name": …,        # 2  (account display_name)
  "participant_email": …,
  "course_title": …,            # 3
  "course_code": …,
  "completed_at": "…",          # 4
  "location": null,             # 5  self study: not applicable, printed as such
  "program_type": …,            # 6  PROGRAM_TYPE constant
  "credit": "0.4",              # 7  as text, one decimal
  "field_of_study": …,          # 7
  "national_registry_id": null, # 8  only if may_claim_registry at completion
  "state_registrations": [{state, number}],   # 9
  "time_statement": …,          # 10 TIME_STATEMENT
  "other_statements": …,        # 11
  "knowledge_level": …, "package_versions": {…}, "passing_pct": 70,
  "score_pct": …, "recommended_credit_basis": …,
  "developed_by": …, "reviewed_by": …,   # names and credentials only
  "snapshot_version": 1
}
```
Every value is copied at completion time from the rows as they stand
then. Nothing in the snapshot is ever re-read from the live tables.

Constants in `app/constants/enrollment.py`: `ENROLLMENT_DAYS = 365`
(9.02.2(3), with the paragraph quoted), `CERTIFICATE_DEADLINE_DAYS = 60`
(9.01). In `app/constants/certificate.py` (003's file): `PROGRAM_TYPE =
"Self study"` — deliberately not "QAS Self Study", which is a Registry
program designation superCPE may not use until `registry_status` is
registered; comment says so and points at Phase C.

## Tasks

1. **Models and migration** as above. Backfill: none. The 007 preview
   attempts stay valid with a null `enrollment_id`.

2. **`app/services/enrollments.py`:** `enroll(db, account, course,
   created_by, source)` — refuses unless the course is published, the
   account is an active participant, and no active enrollment exists;
   pins `package_versions` from the course's current lessons; sets
   `expires_at`. `status(enrollment)`. `list_for_account`,
   `list_for_course`. `packages_for(enrollment)` — the pinned package
   rows, which the player and assessment use instead of the course's
   current lessons. `progress(enrollment)` — per lesson: furthest
   seconds, review questions answered/total; `assessment_available` is
   true iff every pinned review question has an answer and status is
   active.

3. **Player re-gating.** The 006 endpoints gain enrollment-scoped
   variants under `/api/v1/my/enrollments/{id}/lessons/{package_id}/play`
   and `…/review/{question_key}`, behind `require_role("participant")`
   and ownership (a foreign enrollment is 404). Play serves the *pinned*
   package (video URL, blocks, questions). Review grading persists a
   `review_answers` row and returns exactly what 006 returned. A
   `PUT …/progress` records `furthest_seconds` (monotonic: never
   lowered). The admin/reviewer preview endpoints are untouched.

4. **Assessment re-gating.** `assessment.start` for a participant takes
   the enrollment: refuses if status is not active (naming expiry or
   completion), if `assessment_available` is false (naming the unanswered
   review questions by lesson), or if `RETAKES_ALLOWED` is exhausted
   (count failed attempts on this enrollment). Questions come from the
   pinned packages. `submit` past `expires_at` is refused and the open
   attempt is abandoned as failed (6.01.2: the assessment must be
   completed by the expiration date). `result` is unchanged in shape —
   the failed-attempt no-feedback rule from 007 stays exactly as tested.

5. **Completion.** In the same transaction as a passing `submit`:
   `completions.create` — reads the course's `recommended_credit`
   (refuses the submit with a 409 if the credit is stale; this cannot
   happen on a published course but the check is defense in depth),
   builds the snapshot from the live rows, reads `may_claim_registry`
   *now* and sets item 8 accordingly, assigns the certificate number and
   token. If the sponsor's issuance fields (see Decisions) are
   incomplete, the completion is still recorded (the 9.02.2(1) record
   does not wait on the sponsor's paperwork) and the snapshot is still
   frozen, but the PDF is not rendered and the participant sees "Your
   completion is recorded; your certificate will be issued shortly."
   Render happens later via the admin action in task 7.

6. **Certificate rendering.** `app/services/certificates.py`:
   `render(snapshot) -> bytes` — a one-page PDF from the snapshot dict and
   nothing else (it must not take a db session). Layout: sponsor name
   and legal name, "Certificate of Completion", participant name, course
   title and code, completion date, program type, credit with field of
   study, the time statement verbatim, state registrations, other
   statements, developed-by / reviewed-by line, certificate number, and
   the verification token as a short URL placeholder for 018. Item 8
   prints only when present in the snapshot. Item 5 prints "Not
   applicable (self study)". Store the first render at
   `certificates/<certificate_number>.pdf` and set `certificate_key`;
   `GET /api/v1/my/completions/{id}/certificate.pdf` streams that object.
   Re-rendering from the snapshot must produce the same text content
   (assert by extracting text in the test); byte-identity is not required.

7. **Admin.** Under `/api/v1/admin`: `POST /courses/{code}/enrollments`
   (email of an existing participant), `GET /courses/{code}/enrollments`
   (status, expiry, progress summary), `GET /courses/{code}/completions`,
   `POST /completions/{id}/render` (renders if the issuance fields allow;
   422 naming the missing fields otherwise),
   `GET /completions/{id}/certificate.pdf`. `readiness.check` gains a
   sponsor-level (not course-level) finding `certificates_overdue` (warn)
   listing completions older than `CERTIFICATE_DEADLINE_DAYS` with no
   render — shown on `/admin/sponsor` beside the launch-readiness panel.

8. **Deletion and unpublish.** `delete_course` refuses while any
   enrollment exists (422, naming the count). `unpublish` does not affect
   in-flight enrollments: they are pinned and continue; it only stops new
   ones. The admin course page says so: "N participants are enrolled on
   the current versions and will keep them."

9. **Frontend.**
   - `/my/courses` (participant home, the post-login landing for that
     role): each enrollment as a card — title, status, expires on, lessons
     watched, review questions answered, and one primary action:
     Continue / Take the assessment / Retake (N left) / View certificate /
     Expired.
   - `/my/courses/:enrollmentId` — the 004 course page facts, then the
     lesson list with progress, mounting the 006 player per lesson
     through the enrollment endpoints; the assessment link enabled only
     when available, with the reason otherwise.
   - Assessment and result pages reuse 007's components with the
     enrollment endpoints; a passed result shows the completion date,
     credit, and the certificate download (or the "will be issued
     shortly" line).
   - Admin course page gains an Enrollments card (enroll-by-email form,
     table) and a Completions card (table with certificate status and
     Render / Download). `/admin/sponsor` shows overdue certificates.
   - Nothing participant-facing renders "National Registry" unless the
     snapshot carries item 8.

10. **Contract.** No change to `docs/course-package.md`. Say so.

## Tests (`tests/test_enrollments.py`, `tests/test_completion.py`, `tests/test_certificates.py`)

- Enroll: `expires_at` is exactly 365 days after `enrolled_at`;
  `package_versions` pins the current versions; second active enrollment
  refused; enrolling on a draft course refused; enrolling a reviewer
  refused.
- Pinning: after enrollment, `update_version` on the course (unpublish →
  update → re-review → republish) leaves the enrollment serving the old
  package; a new enrollment gets the new one.
- Player: review grading persists the answer; re-answering updates; a
  participant cannot reach another participant's enrollment (404, not
  403); progress never decreases.
- Assessment: start refused with the unanswered review questions named;
  start refused after expiry; start refused when retakes are exhausted,
  naming `RETAKES_ALLOWED`; submit after expiry abandons the attempt as
  failed; a failed result carries no per-question data (re-assert 007's
  payload walk through the enrollment path).
- Completion: a passing submit creates exactly one completion in the same
  transaction; `credit_awarded` equals the course's award as `Decimal`;
  `completed_at` equals the attempt's `submitted_at`; certificate number
  is unique and year-prefixed; the snapshot carries all eleven items.
- Snapshot immutability: after completion, change the course title, the
  sponsor name, the participant display name, and the state
  registrations; the snapshot and the re-rendered PDF text are unchanged.
- Item 8: with `registry_status = not_registered` the snapshot's
  `national_registry_id` is null and the PDF text lacks "National
  Registry"; with `registered` and an ID, both are present. Flipping
  status *after* completion changes neither.
- Issuance fields: with a blank `legal_name` the completion is recorded,
  no PDF exists, the participant payload says pending; after filling it,
  `POST /completions/{id}/render` produces the PDF — and, deliberately,
  the legal name filled *after* completion is not on it (see Decisions).
- `certificates_overdue` lists a 61-day-old unrendered completion and not
  a 59-day-old one.
- Delete course with enrollments refused; unpublish leaves an active
  enrollment's status `active` and its player working.
- All prior tests pass; the count goes up.

## COMPLIANCE.md rows

Add or append:

| 9.02.2(3) | expiration date, no longer than one year from enrollment | 010 | `ENROLLMENT_DAYS` in `app/constants/enrollment.py`; `expires_at` set at `enroll`; `assessment.start`/`submit` refuse past it | One year uniformly; the longer "integrated learning plan" allowance is not modeled. |
| 6.01 | (append) | 010 | Completion exists only as a row created inside the passing `submit` transaction, keyed to a participant account through the enrollment | — |
| 6.01.2 (re-takes) | "at the sponsor's discretion" | 010 | `RETAKES_ALLOWED` (007 constant) enforced per enrollment at `assessment.start` | The retake count is a policy; 011's policies page must state it. |
| 9.01 | (existing row; append) | 010 | `certificate_snapshot` on `completions` freezes items 1–11 at completion; `render` in `app/services/certificates.py` reads the snapshot only; item 8 present only when `may_claim_registry` was true at completion; `PROGRAM_TYPE` is "Self study", never "QAS" | Delivery "as soon as possible … not exceed 60 days" is reported (`certificates_overdue`), not enforced; email delivery is 018. Location (item 5) printed as not applicable. |
| 9.01.1 | (append) | 010 | `sponsor_legal_name` in the snapshot is the awarding entity printed on the certificate | — |
| 9.02.2(1) | (existing row; append) | 010 | `completions` (participant via enrollment, `credit_awarded`, `completed_at`), never deleted; `review_answers` and `lesson_progress` retain the engagement record | Export is 011. |
| 9.02 | (append) | 010 | `enrollments`, `completions`, `review_answers`, `attempts` FK RESTRICT to accounts and packages; course delete refused with enrollments | Period constant still 011. |

## Acceptance

1. Migration runs on the 009 database; 007's preview attempts still list.
2. As admin: enroll the participant test account on ASC842-PCX (it must
   be published — see the note at the end); the enrollment shows a
   one-year expiry and the pinned versions.
3. As the participant: `/my/courses` shows the course; the player works
   through every lesson; answers persist across reload; the assessment
   link is disabled until the last review question is answered, and says
   which are missing.
4. Fail the assessment once: the result shows score and retakes left, no
   per-question detail. Pass it: a completion appears with the credit and
   date; with the sponsor profile complete, the certificate PDF downloads
   and contains every 9.01 item except item 8, and the words "National
   Registry" appear nowhere.
5. As admin: edit the course title (unpublish first); the participant's
   certificate is unchanged; a new enrollment sees the new title.
6. Delete the course: refused, naming the enrollment.
7. `pytest`: all pass; count exceeds 137.

## When done

- Changelog per CLAUDE.md, including the justification for the PDF
  library chosen (prefer a pure-Python one with no system dependencies;
  say which and why), the pinning trade-off (a correction re-exported
  mid-enrollment does not reach in-flight participants), and the
  `missing_fields` split below restated.
- COMPLIANCE.md rows above.
- Improvement note for ROADMAP if you see one; specifically whether an
  admin should be able to *extend* an expiry (the Standard says "no
  longer than one year from … enrollment", which reads as a cap, not a
  clock that can be reset — say what you concluded).
- List out-of-scope hits, especially anything 011's bundle will need that
  is not yet in a row.

## Decisions to restate in the changelog

- **`missing_fields` split.** 003 made `registry_status` a
  certificate-blocking missing field. That was right for the claim ("no
  certificate may say National Registry until it is true") and wrong for
  issuance: a sponsor that is not on the Registry may still issue a
  certificate — it simply cannot print item 8 — and Phase B's NASBA
  application needs a sample certificate before membership exists. So:
  `missing_fields()` gains a `for_issuance` view that excludes
  `registry_status`; issuance gates on that view; item 8 gates on
  `may_claim_registry`, snapshotted at completion. 003's COMPLIANCE row
  is appended to say so.
- **Snapshot at completion, not at render.** If the sponsor's legal name
  is blank when a participant completes, the certificate that eventually
  prints will be missing it, because the snapshot is the truth and it was
  taken when the credit was earned. The fix is to keep the profile
  complete *before* opening the site — which the launch-readiness panel
  already says — not to let a later edit rewrite what a participant
  earned. `certificates_overdue` is the safety net.
- **Pinning.** An enrollment is served the package versions it started
  on. Published courses are immutable (008), so a version change already
  implies unpublish → re-review → republish; in-flight participants keep
  what they enrolled on, and the certificate snapshot records exactly
  which versions.

## A note for the human before acceptance

Acceptance item 2 needs ASC842-PCX published, and today the only way it
is published in the dev database is the 008/009 test review by a
fictitious reviewer. That is fine for local acceptance and must not
survive to deployment: before 012, unpublish, delete the fictitious SME
and their review, and re-review with the real second CPA. Put that on the
012 checklist now so it is not forgotten.
