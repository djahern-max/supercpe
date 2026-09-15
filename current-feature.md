# Feature 037 — Reader position indicator

## Goal

A participant in the reader can't tell where they are in the course. The reader
has a "START HERE" label with a bar under it that appears to be a progress bar, but
the bar shows no progress. The breadcrumb reads the placeholders
`My courses / course / lesson` instead of real names. The lesson number appears only
in the URL.

Add a small, quiet indicator: **Lesson 4 of 6 · Section 2 of 7**, a progress bar
that actually fills, and a breadcrumb with real names.

## Standards touched

- **4.05.3(4)** — self-study instructional materials must include "instructions to
  participants regarding navigation through the course, course components, and
  course completion." A position indicator supports this. It is not a substitute
  for the written navigation instructions, which stay as they are.
- No change to gating, credit, or completion rules.

## In scope

1. **Findings first.** Before changing anything, report:
   - What the "START HERE" label and bar are. Is it a section-group heading, the
     027 stepper, or a progress bar? What value drives it, and why does it show
     empty?
   - Where the breadcrumb gets `course` and `lesson`, and why real names don't
     appear.
   - What the reader payload already provides: course title, lesson title, lesson
     position and count, section position and count, and completed or unlocked
     state.
   - Whether the REFERENCE group (and any similar non-gated group) is part of the
     gated section sequence.
   - Why each section shows its title twice (the eyebrow "HOW THIS COURSE WORKS"
     plus the heading "How this course works"). The lesson Markdown's own H1 ("Verifying the
     output") also repeats the page title. This item is **findings only**: report it,
     don't fix it.
2. **Position line** under the page title, in small muted text:
   `Lesson {n} of {m} · Section {i} of {k}`.
   - `n`/`m` are published lessons in the enrolled course version.
   - `i`/`k` are positions in this lesson's gated section sequence. Reference sections
     are excluded from `k` unless findings show they are gated.
   - Values come from the API, never parsed from the URL.
3. **Progress bar.** Its fill is the share of this lesson's gated sections the
   participant has completed. A completed section is one whose review gate has been
   passed, as the backend already defines it. The bar needs an accessible label,
   e.g. `aria-label="2 of 7 sections complete"`. The fill must match server state
   after a reload. If findings show "START HERE" is a group heading and not a
   progress bar, keep the heading and add the bar next to the position line.
4. **Breadcrumb.** Replace the placeholders with `My courses / {course title} /
   Lesson {n}: {lesson title}`, and link the course crumb to the course page.
5. **API.** If the reader payload lacks any of the values above, add them to the
   existing reader response. Don't add a new endpoint.

## Out of scope

- Fixing the duplicate headings (findings only; that becomes a later feature).
- Course-level progress on the My courses page.
- Any change to gating, unlock rules, the qualified assessment, or credit math.
- Changes to the course package contract or video-tool.
- Visual redesign of the reader beyond the indicator, bar, and breadcrumb.

## Locators

Report actual paths in the findings. Starting points: the reader page and its
stepper/contents components under `frontend/src/` (023 reader, 027 stepper), and
the reader route and schema under `backend/app/`.

## Data model

None expected. Section completion state should already exist for gating. If it
doesn't, stop and flag it; don't add a table.

## Tasks

1. Findings report.
2. Backend: extend the reader payload with course and lesson titles and all
   position and progress values (if missing).
3. Frontend: position line, working progress bar, real breadcrumb.
4. COMPLIANCE.md row.

## Tests

Backend:
- For lesson 4 of 6 with 7 gated sections and 2 completed, the reader payload returns
  `lesson_position=4`, `lesson_count=6`, `section_count=7`, `sections_completed=2`
  (use the names that fit the existing schema).
- Reference sections are excluded from `section_count` (or included, if findings
  show they are gated; the test should match whichever is true).
- A participant can't use the payload to learn anything about another participant's
  progress.

Frontend:
- Renders `Lesson 4 of 6 · Section 2 of 7` from a mocked payload.
- The bar's fill and aria-label reflect completed sections.
- Selecting a different section updates the section position.
- Completing a section's review gate advances the bar without a reload.
- The breadcrumb shows course and lesson titles, and no `course` or `lesson`
  placeholder text.

## COMPLIANCE.md rows

- 4.05.3(4): the reader shows the participant's lesson and section position and
  section progress, supplementing the course's navigation instructions. Cite 037.

## Acceptance

1. Findings report delivered, including the duplicate-heading finding.
2. All tests pass; pyflakes, oxlint, and both suites are green.
3. Locally, on lesson 4 of a 6-lesson course, the reader shows the position line,
   a bar that fills as review gates are passed, and a real breadcrumb.
4. After a reload, the position and bar match server state.
5. Operator-only (list under Known gaps if not run): deploy, then a browser check
   on supercpe.com.

## When done

Append CHANGELOG entry 037 in the existing format (What changed / Standards
touched / Decisions / Known gaps). Put the duplicate-heading finding under Known gaps.
