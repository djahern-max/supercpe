# Current Feature

## Feature 020, Per-jurisdiction credit policy

## Goal
A participant who has told superCPE their state of licensure sees, beside
a course, what their board's rules mean for the recommended credit — the
accepted rounding increment (7.01) and any non-technical cap that applies
to the course's field of study. Every displayed fact is one the admin
verified against a source on a date; the table **ships empty** and stays
empty until Dane fills rows he has checked. The Standard puts the final
check on the CPA ("should refer to the respective state board
requirements", 7.01); this feature is superCPE doing part of that lookup
for them, never speaking for a board.

## Read before building
- 7.01/7.01.1 from the 2026 Standards (increments, rounding down) — cite
  the Standard in code comments, not this spec.
- The 2024 Fields of Study document (also in the repo's PDFs) for the
  technical / non-technical classification of each field — the mapping
  in scope below is transcribed from that document, not from memory.
- 015's `US_JURISDICTIONS` (this is the reuse it was placed for), 017's
  optional `accounts.state`, 005's stored credit, and 016's course
  payload with its key-set test — which this feature deliberately does
  **not** touch (see routes).

## In scope

### 1. Fields of study classification
`constants/fields_of_study.py`: the NASBA fields with a
technical/non-technical flag per the 2024 document, transcribed with a
comment naming the document. Then look at how courses store
`field_of_study` today: if it is free text, validate it against this
list on course create/edit (existing courses with a non-matching value
are flagged in admin readiness, not broken); if 004/005 already
constrain it, just wire the lookup. A course whose field is unknown to
the list gets no classification and no jurisdiction hint.

### 2. Jurisdiction policy table
One row per jurisdiction code (unique, validated against
`US_JURISDICTIONS`), admin-maintained:
- `credit_increment`: enum `one_fifth` / `one_half` / `whole` /
  `unknown` (default)
- `non_technical_cap_note`: nullable free text — caps are per reporting
  period and cannot be computed, only quoted (e.g. "no more than half
  of total hours may be non-technical")
- `source`: free text/URL naming where the rule was read — required to
  display
- `verified_on`: date — required to display
- `notes`: nullable, admin-only
A row is **displayable** only when `credit_increment` is not `unknown`,
and `source` and `verified_on` are set. No seed data beyond the 55 empty
codes (or create-on-edit; whichever is simpler — but never shipped
increments). Docstring: reference data, not CPE records.

### 3. Participant state
- Participants may set or change their own `state` from their account
  page (the 017 column; dropdown from `US_JURISDICTIONS`, clearable).
  It is their claim about themselves, not a credential — no verification
  step. Admin-side state edit, if 009's account admin has one, is
  untouched.

### 4. The hint
- `GET /api/v1/courses/{code}/jurisdiction-note` — authed participant
  only; 404 when the participant has no state, the jurisdiction row
  isn't displayable, or the course isn't publicly renderable. **A
  separate endpoint on purpose**: the 016 public payload and its
  key-set test stay byte-for-byte untouched, and the hint is inherently
  per-viewer, which a public cached payload should never be.
- Response: the jurisdiction, the increment; when the increment is
  coarser than one-fifth, the recommended credit rounded **down** to
  that increment (7.01.1's arithmetic — e.g. 1.4 under one-half → 1.0),
  labeled as computed; the cap note **only when the course's field is
  non-technical**; `verified_on`; and a fixed sentence that boards of
  accountancy have final authority on acceptance of CPE credits.
- Frontend: a small "For your board (NH)" panel on the course page,
  rendered only when the endpoint answers, showing exactly the
  response; the final-authority sentence is not truncatable. Nothing
  for anonymous visitors, participants without a state, or unverified
  jurisdictions — absence, not a stub asking them to check back.
- **Never on the certificate.** The certificate's credit and 50-minute
  statement (9.01 item 10) are untouched; a test pins the certificate
  render free of jurisdiction content.

### 5. Admin
- `/admin/jurisdictions`: the 55 rows, inline edit of the five fields,
  a Displayable column derived live, and a staleness nudge (admin-only)
  on rows whose `verified_on` is older than 12 months. Routes under
  `/admin`, swept by 009's walk automatically.
- OPERATIONS.md: a short "Jurisdiction policies (020)" section — the
  displayability rule, that rows are Dane's research responsibility
  with sources, and the annual re-verification nudge.

### 6. Tests and docs
- Displayability matrix (unknown increment / missing source / missing
  date → 404 on the hint; complete row → 200).
- Rounding: one-fifth board shows the stored credit unchanged;
  one-half and whole boards show the computed round-down; the
  computation never alters 005's stored value (assert the course row
  is unread-only… i.e. unchanged).
- Cap note appears only for non-technical fields; ASC842-PCX
  (Accounting, technical) never shows one.
- No-state participant, anonymous, and coming_soon all 404; the 016
  key-set test and 015 router walk pass untouched.
- Certificate render pinned jurisdiction-free.
- COMPLIANCE.md: a 7.01 row — superCPE awards in one-fifth increments
  (005 unchanged) and surfaces verified board increment differences to
  the claiming CPA, who retains the Standard's own duty to check;
  final authority stays with boards.

## Out of scope
- Tracking a participant's reporting-period totals or whether they are
  near a cap — superCPE cannot know their other CPE and must not
  pretend to.
- Auto-populating or scraping board rules; any shipped increment
  values.
- Changing 005's calculation, the 0.2 minimum, or certificate content.
- State-specific certificate statements or registration numbers (9.01
  items 9/11) — nothing today requires them; if a board someday does,
  that is its own feature.
- Waiting-list invitations (021).

## Acceptance
1. Fresh database: no jurisdiction hint appears anywhere for anyone.
2. Admin fills NH with one-fifth increment + source + date: a NH
   participant sees the panel with the stored credit and the
   final-authority sentence; a participant with no state, and an
   anonymous visitor, see nothing.
3. Admin sets a test row to one-half: the panel shows the computed
   round-down labeled as computed; 005's stored value is unchanged
   everywhere else.
4. Cap note renders only when the course's field is non-technical per
   the transcribed mapping.
5. The 016 key-set test, the 015 router walk, and the certificate
   render test all pass untouched.
6. Full suite green; changelog entry written; the fields-of-study
   mapping's changelog line names the 2024 document as its source.

## Notes for Claude Code
- The rounding helper is three lines and must round down, never
  half-up; property-test it across increments if quick.
- ROADMAP: mark 020 built ahead of ship. After this, Phase C code is
  021 plus the flip.
