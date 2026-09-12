# Feature 027 — Participant flow: every screen names the next step

Corrective feature from the 2026-09-12 participant walkthrough of `ATO`
(a participant account, self-created, reading the study guide, watching
the clips, answering all review questions, and failing the assessment
to exhaustion). Presentation and navigation only. No data model, no
change to what is gated or how, no change to credit, questions, or
certificates. Anything that turns out to need a design decision is
reported, not built.

## The findings

**W1. The reader is a wall of text.** Unlocked sections render as one
long page. A participant cannot tell where they are, how much is left,
or that a question is waiting at the bottom.

**W2. No direction after the last review question.** When the final
gate clears, nothing changes on screen. The participant found "Take
assessment" only by navigating back to the course page.

**W3. No direction when a video ends.** The clip stops; the page does
nothing. Nothing says "continue reading" or "next lesson".

**W4. No rewind or fast-forward on video.** The participant could not
move within a clip. (Task 0 must establish which player this was; see
below — the two players have different rules.)

**W5. No direction after a failed assessment.** The failed result says
"no retakes left, consider retaking the course"; the course page then
says "The assessment is not available yet: No re-takes left on this
enrollment." Two messages, no next step. The *exit* from this state is
028 (exhausted enrollments); the honest wording is 027.

**W6. 025's recorded chrome gaps** on the same surfaces: duplicate
Sign out and email on `/my/courses` and the review pages; `/login` has
no create-account link; no footer, so `/policies` is reachable only
from the course page and `/register`.

## Goal

A participant never has to guess what to do next. The reader shows one
section at a time with a table of contents and a Continue affordance;
the gate question sits where the section ends; clearing the last gate
puts "Take the assessment" in front of the participant; a finished clip
says where to go; a failed result says exactly what the sitting count
means; the chrome has one Sign out, a create-account link, and a footer.

## Read before building

- `docs/decisions/2026-09-01-text-first.md` and the `reader.py`
  docstring. Two rules are not negotiable here: **the gate is
  server-side** (a locked section's markdown is not in the payload at
  all), and **no answer key reaches the browser**. Every change in this
  feature is client presentation of a payload the backend already
  serves. If a task seems to need a new read endpoint or a change to
  `reader.build`, stop and report.
- The 023 decision on seeking: supplemental clips in the reader carry
  **no seek lock**. The video-only course player keeps its forward-seek
  lock; changing that is a separate decision and out of scope.
- 010's rule that progress never decreases. Nothing here writes
  progress; the section the participant is looking at is browser
  state, not a record.
- 023c's D2 fix (review feedback must persist, not flash). Do not
  reintroduce it by restructuring the reader.

## Locators — read these paragraphs in the 2026 Standards PDF before writing code

Pages are the printed page numbers in
`docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`.

- **4.05.3** (pages 7–8), items 4 and 5: instructional materials must
  include "instructions to participants regarding navigation through
  the course, course components, and course completion" and review
  questions "with feedback". The reader's front-matter "How this course
  works" block is how item 4 is met today; the stepper must show it
  first and must not hide it.
- **5.01.2.1** (page 9): review questions "placed throughout the
  program in sufficient intervals". The stepper places each question
  where the package placed it (`after_section`); it does not move,
  batch, or defer questions.
- **5.01.2.2** (page 10): feedback must at minimum say "correct" or
  "incorrect". The inline question keeps 023c's persistent feedback.
- **6.01.2** (page 13): "The number of re-takes a participant is
  permitted to take is at the sponsor's discretion." (page 14) on a
  failed assessment the sponsor "may not provide feedback". The failed
  result page may say how many sittings remain and what the policy is;
  it still shows nothing per question.
- **8.01.1** (page 20): policies "formalized, published, and made
  available". The footer adds a second path to `/policies`; it does not
  change what the policies say.

## In scope

### 1. Task 0 — establish, then decide scope

Answer each in the changelog before writing code:

1. Which video did the walkthrough watch — a supplemental clip inside
   the reader (`media[]`, `placement.afterSection`), or the video-only
   course player? Do supplemental clips render in the reader today
   (023b listed them out of scope; 023c may have added them)? If they
   do not render at all, W3/W4 apply only to the video-only player.
2. On the video-only player, is *backward* seeking allowed today, or
   does the lock block both directions? 023 describes a forward-seek
   lock. If rewind is blocked, that is a defect to fix here; nothing
   in the Standards or the recorded decision asks for it.
3. How does the reader component receive sections — one array with
   `locked`/`markdown: null` per section? Confirm the stepper can be
   built on that payload unchanged.
4. Where does the frontend learn `assessment_available` and the
   unanswered list — the course page payload, the reader payload, or
   both? The "take the assessment" call to action needs it inside the
   reader.
5. What does the failed-result payload carry about sittings —
   `retakes_remaining`, a boolean, or only the refusal message from
   `start_for_enrollment`?
6. Does `/policies` render the derived `retake_policy_text()`? The
   failed result should link to it, not restate it.

### 2. Reader as a section stepper (W1)

- One section on screen at a time, in manifest order. A persistent
  table of contents (sidebar on wide viewports, collapsible on narrow)
  lists every section with its state: read, current, unlocked-unread,
  locked. Locked entries show the title only (the title is already in
  the payload; the markdown is not, and stays not).
- Front matter renders first, always, including the "How this course
  works" block. Glossary and appendix sections are listed in the table
  of contents under a "Reference" heading and open at any time, as
  today.
- Continue: at the end of a section with no question after it, a
  Continue button opens the next section. At the end of a section
  with questions after it, the questions render inline beneath the
  text (all of them, in package order) and Continue is disabled until
  every one is answered — then it reads "Continue" and opens the newly
  unlocked section. This is presentation of the server's gate, not a
  second gate: the button asks for the payload again and shows what
  the server unlocked.
- Progress line above the section: "Section 4 of 14" and a thin bar.
  Counts every body section; reference sections are excluded and say
  "Reference" instead of a number.
- Position is remembered in the URL (`?section=<key>` or a hash) so
  reload and back/forward work; nothing is written to the server.
  Opening the lesson with no section in the URL lands on the first
  section not yet read if that can be derived from the payload
  (locked state and answered questions), otherwise on front matter.
- Search results and glossary links continue to open the reader at
  the target section; verify they set the URL position.
- Keyboard: left/right arrows or the buttons; no new dependency.

### 3. Completion call to action (W2)

- When the payload reports every review question answered and the
  qualified assessment available, the reader shows a completion card
  after the last body section: "You've finished the study guide" with
  a primary "Take the qualified assessment" link to the existing
  assessment route, and a secondary link back to the course page.
- If the course has more than one lesson, the card names the next
  lesson instead when one remains, and the assessment only when the
  whole course is read. Use whatever the course payload already
  exposes; do not add a field.
- The course page shows the same state without hunting: the
  Registration/progress section's next action is a primary button —
  "Continue reading (Section 4 of 14)", "Take the qualified
  assessment", or "View your certificate" — never only a status line.
- `/my/courses` cards carry the same next-action button.

### 4. Video direction and controls (W3, W4)

Supplemental clips in the reader (if Task 0.1 finds them rendered):

- Native controls on (`controls` attribute), no seek restriction of
  any kind. This is the recorded 2026-09-01 decision; the spec
  restates it so nobody re-adds a lock "for consistency".
- On `ended`, an overlay or line beneath the clip: "Continue reading"
  that scrolls to or opens the following content (the next section
  or the question placed after it).

Video-only course player:

- Backward seeking allowed. If Task 0.2 finds it blocked, fix it and
  say so in the changelog. Forward-seek lock untouched.
- Play/pause and a rewind-15-seconds control if the player has no
  native controls exposed. Fast-forward stays blocked by the lock;
  the control set must not imply otherwise.
- On `ended`: the next step — the review questions for this lesson if
  any are unanswered, else the next lesson, else the assessment (same
  derivation as section 3).

### 5. Failed-result and exhausted wording (W5)

Wording only. The exit from exhaustion is 028; do not build a
re-purchase path, a reset, or an admin action here.

- Failed result with sittings remaining: score, the passing threshold,
  "You have N re-takes left on this enrollment", a primary "Re-take
  the assessment" button, and a link to the study guide. Nothing per
  question (6.01.2).
- Failed result with none remaining: score, the threshold, "You have
  used all N re-takes on this enrollment", a link to the retake policy
  on `/policies` (Task 0.6), and the sponsor's contact address from
  the sponsor profile with one sentence: "Contact us about re-enrolling."
  The study guide stays readable (the enrollment is not expired or
  voided); say so.
- Course page in the same state: one message, not two. Replace "The
  assessment is not available yet: No re-takes left on this
  enrollment" with the same three-part wording as the result page.
  The "not available yet" phrasing is reserved for unanswered review
  questions, which is the only case where "yet" is true.
- Remove any remaining video wording on text courses that 023c's F1
  missed (grep the frontend for "watch", "re-watch", "video" on
  participant surfaces and list what was found).

### 6. Chrome (W6)

- Remove the page-level email/Sign out rows from `MyCourses` and
  `ReviewHeader`; the 025 site header is the one place. Keep
  breadcrumbs.
- `/login`: a "Create account" link below the form, rendered only at
  `open` or with a session — the same `siteFace()` decision the header
  uses, so the coming-soon landing page still advertises nothing.
- A site footer under the same render rule as the header (null while
  coming-soon, null under `/admin`): links to `/policies`,
  `/how-it-works`, and the sponsor's contact address. No course fact,
  no "National Registry", no sponsor statement, never reads
  `may_claim_registry` — the same test 025 pins for the header.

## Out of scope (report, do not build)

- Any exit from the exhausted state: derived `exhausted` status,
  re-purchase, goodwill re-enrollment, resetting counts (028).
- Removing or changing the video-only player's forward-seek lock.
- Subscription billing, the header "Subscribe" affordance (029);
  Google sign-in (030).
- Server-side reading position or "last read" records. If it seems
  necessary, report why — it would be a new participant record and
  needs a retention decision.
- Reading-time estimates anywhere (023b's rule: it would read as a
  second credit figure).
- Review-question placement density in `ATO` (content, video-tool
  side).
- Anything in the site-open gate, email, or Stripe.

## Locators — code

Find by grep and record the actual paths in the changelog:

- Frontend: participant reader (`/my/courses/:id/lessons/:id`, the
  023 reader component), video player component, `MyCourse`,
  `MyCourses`, `MyAssessment` result view, `Login`, `SiteHeader`,
  `SiteContext.jsx` (`siteFace()`), `ReviewHeader`, `Policies`.
- Backend (read only, to confirm payload shapes): `reader.build`,
  `schemas/reader.py`, `enrollments.progress` and
  `retakes_remaining`, `assessment.result`, the course-page payload,
  `policies.retake_policy_text`.

## Data model

None. If a migration appears necessary, stop and report.

## Tests

Frontend (vitest, baseline 30):

- Stepper: renders exactly one body section's markdown at a time; a
  locked entry in the table of contents shows a title and never a
  body; Continue is disabled while any inline question is unanswered
  and enabled after all are answered (mock the payload before and
  after); progress line counts body sections only; URL position
  round-trips.
- No answer key: walk the rendered DOM and the mocked payload
  assertions from 006/023 — `is_correct` and feedback absent until
  the grading response.
- Feedback persists after the payload refetch (re-assert 023c D2
  through the new component).
- Completion card appears only when the payload says every question is
  answered and the assessment is available; names the next lesson when
  one remains.
- Video: reader clip has `controls` and no seek handler; on `ended` the
  continue affordance appears. Video-only player: backward seek
  allowed, forward seek still refused, `ended` shows the derived next
  step.
- Failed result: N-remaining and none-remaining variants render the
  specified wording; neither renders per-question data.
- Chrome: one Sign out on `/my/courses` and `/review`; `/login` shows
  Create account at open and not in coming-soon signed out; footer
  absent in coming-soon signed out, absent under `/admin`, present at
  open; footer text contains no course fact and no Registry string.

Backend: no change expected. Suite stays at 464; if a backend test
changes, say why.

## COMPLIANCE.md rows

- 4.05.3(4): append to the existing row — the reader now presents the
  navigation instructions first in a stepper and the course page and
  `/my/courses` show the next action; the paragraph is satisfied by the
  same content as before, reached more reliably. Not a new way of
  meeting it.
- 5.01.2.1: append — question placement in the stepper is the
  package's `after_section`, unchanged; the stepper presents the
  server's gate and adds none of its own.
- 6.01.2 (re-takes): append — the failed result and course page now
  state the sitting count and link the published policy; still no
  per-question feedback on a failed attempt.
- 8.01.1: append — `/policies` gains the footer link on every open
  surface.

## Acceptance

1. Local: enroll a participant in `ATO`, open lesson 2. The reader
   shows front matter, then one section at a time with the table of
   contents; a locked section cannot be reached and its text is not in
   the network response; the question after sec-01 renders inline and
   Continue enables only after it is answered; feedback stays on
   screen.
2. Answer all five review questions; the completion card appears with
   "Take the qualified assessment"; the course page and `/my/courses`
   show the same button.
3. A supplemental clip (if rendered) has native controls, seeks both
   ways, and shows "Continue reading" on end. The video-only player
   (on `ASC842-PCX` or the fixture) rewinds, still refuses forward
   seek, and shows the next step on end.
4. Fail the assessment four times. After each failure the result names
   the sittings left; after the fourth, the result and the course page
   show the same exhausted wording with the policy link and contact
   address, and the study guide still opens.
5. Signed out at `open`: `/login` shows Create account; every open page
   has one header, one footer, one Sign out when signed in. In
   `coming_soon` signed out: no header, no footer, no create-account
   link on `/login`.
6. Typecheck and check pass; frontend and backend suites green.
7. Production (operator): deploy with the sha from
   `git rev-parse --short origin/main`; repeat 1, 2, and 4 as the test
   participant.

## When done

Write the changelog entry only after acceptance 7 passes on
production. Include the Task 0 answers, the actual file paths, the
grep list from section 5, and whether rewind on the video-only player
was a fix or already worked. Append only. Add to ROADMAP.md improvement
notes: "028 — exhausted enrollments: derived status, re-purchase or
goodwill re-enrollment (sponsor decision), `retake_policy_text()`
updated" so the exit W5 needs is recorded where the next spec will look.
