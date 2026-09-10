# Feature 023b — Text lessons open the reader, not the player

Corrective feature from the 2026-09-10 production walkthrough (SEC-01 /
course `ATO`, Stages 4+). Fixes only, no redesign. 023 shipped the text
reader; this wires it into the surfaces that still assume every lesson
is a video.

## The defect

A participant enrolled in `ATO` opens `/my/courses/1/lessons/2` and gets
"The lesson could not be loaded." The page calls
`GET /api/v1/courses/ATO/lessons/2/play`, which returns 500:

```
video_url=storage.url_for(package.video_key, VIDEO_URL_SECONDS)
  File "/srv/app/app/storage.py", line 105, in url_for
botocore.exceptions.ParamValidationError: Invalid type for parameter Key,
value: None
```

A `kind: "text"` package has no `video_key`. The admin preview fails
identically, so **the reviewer surface cannot display a text course
either**. A substantive 4.02 review of any text course is impossible
until this ships, which puts this fix on the critical path, not just
the walkthrough.

## Goal

Every surface that opens a lesson (participant, admin preview,
reviewer) dispatches on package kind: text packages open the 023
reader, video packages keep the player. `/play` refuses a text package
cleanly instead of crashing. Review answers given in the reader count
toward the assessment gate exactly as in-video answers do.

## In scope

1. Establish what exists (Task 0) before changing anything.
2. Lesson-page dispatch by package kind: participant, admin preview,
   and reviewer surfaces.
3. Participant reader is **gated** (sections unlock as review questions
   after them are answered); preview and reviewer readers are
   **ungated** (`reader.build(..., gated=False)`, per 023: 4.02 expects
   the reviewer to read the whole guide).
4. Review answers in the reader use the same answer-recording path as
   the video player, so the course page's "N/5 answered" count and the
   qualified-assessment gate ("Unanswered review questions in …") clear
   when all five are answered.
5. `/play` for a text package returns a 4xx with a clear message
   (409 or 422, follow the codebase's existing convention), never 500.
6. Course page and catalog wording for text courses: no "0 minutes of
   video" and no "0:00" lesson duration. Show "Study guide" and the
   section count instead. Do not add a reading-time estimate (it would
   read as a second credit figure beside the computed one).
7. Empty "My courses" page links to the catalog (`/courses`).
8. OPERATIONS.md: the diagnostic sequence's `docker compose logs` step
   fails outside `deploy.sh` because the compose file requires
   `GIT_SHA`. Amend it to use
   `docker logs --tail=50 $(docker ps -q --filter label=com.docker.compose.service=api)`,
   or document exporting `GIT_SHA` from the running image first.

## Out of scope (report, do not build)

- Supplemental clips (`media[]`, `placement.afterSection`) in the
  reader. The reader should not be structured in a way that prevents
  them, but no clip rendering in this feature.
- The "Advance review was impractical (4.02.1)" path. 4.02.1 rests on
  the instructor's or presenter's competence, and self study has
  neither. Whether the path should exist for self study is a separate
  decision; record it as a ROADMAP question, not code.
- Review-question placement density in SEC-01 (no review questions
  after sec-02–04 or sec-10–11; lo-2, lo-5, lo-6 uncovered). Content,
  video-tool side.
- Stripe, email, anything in the site-open gate.

## Locators

Find these by grep and record the actual paths in the changelog:

- Backend: the `/play` route for
  `GET /api/v1/courses/{code}/lessons/{package_id}/play`;
  `backend/app/storage.py` `url_for`; the reader service
  (`reader.build`); the 023 read endpoint
  `GET /api/v1/courses/{code}/lessons/{package_id}/read`; the review
  answer-recording endpoint; the qualified-assessment availability check.
- Frontend: participant lesson page (`/my/courses/:id/lessons/:id`);
  admin preview (`/admin/courses/:code/preview`); reviewer
  (`/review/courses/:code`); course page (`/courses/:code`); catalog
  (`/courses`); My courses (`/my/courses`).

## Task 0 — establish, then decide scope

Answer each in the changelog before writing code:

1. Does a **gated participant** read path exist on the backend (reader
   with `gated=True` behind an enrollment), or only the ungated preview?
2. Does a reader component exist in the frontend, and where is it
   mounted today?
3. Why does the lesson page call `/play` for a text package? (No kind
   check? Kind not in the lesson payload?)
4. How are review answers recorded for video lessons, and is that path
   keyed in a way a text lesson (`after_section`) can use unchanged?
5. **Sponsor statement.** The `ATO` course page renders the NASBA
   sponsor statement ("superCPE is registered with …"). Confirm the
   render condition is `may_claim_registry` and nothing looser. If the
   condition is correct, it is data (the operator set the flag on the
   disposable DB). Say so and change nothing. If the condition is
   wrong, fix it here with a test. 8.01 item 11 applies only "if an
   approved NASBA sponsor."
6. **Review recording.** Can an admin session record a 4.02 review in
   another SME's name, or is the review recorded by the reviewer's own
   session? Report only; do not change it in this feature.

**Stop rule:** if Task 0 finds the gated participant reader (backend
or component) does not exist at all, rather than existing but being
unwired, stop and report. That is a build, and it gets its own spec.

## Data model

None expected. If a migration appears necessary, stop and report.

## Tests

- Participant lesson endpoint/page for a text package returns the gated
  reader payload; `/play` for a text package returns the chosen 4xx,
  not 500.
- Video package: `/play` behavior unchanged (existing tests stay green).
- Gating: a section after an unanswered review question is withheld;
  answering unlocks it.
- Answering all review questions in a text lesson makes the qualified
  assessment available; answering four does not.
- Preview and reviewer read paths are ungated.
- Course page/catalog render no video minutes or duration for a text
  course.
- If Task 0.5 required a fix: sponsor statement absent when
  `may_claim_registry` is false, present when true.
- Full suite green (baseline 432).

## COMPLIANCE.md rows

- 5.01.2.1: review questions in text courses are placed by
  `after_section` and must be answered to proceed; answers gate the
  qualified assessment. Add or update the row to point at the reader.
- 4.02: the reviewer surface renders text courses ungated. Note that
  before 023b a text course could not be displayed to a reviewer.
- 5.01.2.1 "True or false": superCPE excludes **all two-choice
  questions** from the review-question count. That is stricter than
  the paragraph, which excludes only true/false. Record it as a
  deliberate superCPE rule, not Standards text.

## Acceptance

1. Local: ingest SEC-01, enroll a participant, open the lesson. The
   reader renders, sections gate, all five review questions are
   answered in the reader, and the assessment becomes available.
2. Local: the admin preview and the reviewer surface render all 14
   sections ungated.
3. Typecheck and check pass; suite green.
4. Production (operator): push, then deploy with the sha from
   `git rev-parse --short origin/main`. Reload
   `/my/courses/1/lessons/2` as the test participant. The reader
   renders, q-07 through q-11 can be answered, and the course page
   shows 5/5 with the assessment available.
5. Production: the admin preview of `ATO` renders.

## When done

Write the changelog entry only after acceptance 4 and 5 pass on
production. Include the Task 0 answers, the chosen 4xx code, and the
actual file paths. Append only.
