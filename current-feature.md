# Current Feature

## Feature 016, Public catalog and course pages with full 8.01 disclosure

## Goal
When the site opens, the public face of superCPE is a catalog of published
courses and a per-course disclosure page that makes every applicable 8.01
item available in advance, from stored facts, before anyone registers or
pays. A course that cannot disclose completely cannot be published. The
coming-soon landing page (015) disappears at open by design it already has;
this feature builds what stands in its place.

This feature is **built now and ships at open**. Until `site_mode` is
`open`, everything here stays behind the 009 gate exactly as it does today —
nothing in this feature touches `INTENTIONALLY_PUBLIC`. That is the whole
point of building it early: it can be finished, tested, and reviewed through
the hidden login while the site is still coming-soon.

## Why now
015's changelog records the deliberate refusal: the landing page discloses
none of the eleven items because partial disclosure reads as descriptive
material. 016 is the other half of that decision — the page that discloses
all of them. Registration (017) and payment (018) hang off this page later;
they are not here.

## The eleven items (8.01)
The Standard, for sponsors whose courses are developed for sale, requires
these made available in advance. Each maps to a stored fact; the page never
carries a free-typed course claim.

| # | 8.01 item | Source of truth |
|---|-----------|-----------------|
| 1 | Learning objectives | Course record (ingested from the package manifest, 004) |
| 2 | Type of formal learning program | The `PROGRAM_TYPE` constant — the literal string "Self study", never "QAS Self Study" |
| 3 | Recommended CPE credit and recommended field of study | 005's stored credit result (refused if stale) + the course's field of study |
| 4 | Prerequisites | Course field. 8.01.2: precise language so a reader can tell whether they qualify. "None" is a stored value, distinct from blank |
| 5 | Program knowledge level | Course field |
| 6 | Advance preparation | Course field. "None" is a stored value, distinct from blank |
| 7 | Program description | Course field |
| 8 | Course registration and attendance requirements | A published policy (see below) |
| 9 | Refund policy / cancellation policy | Current published version of the 011 policy |
| 10 | Complaint resolution policy | Current published version of the 011 policy |
| 11 | Official NASBA sponsor statement | **Conditional by the Standard's own wording** ("if an approved NASBA sponsor"). Rendered only when `may_claim_registry` is true; while false the item is inapplicable, absent from the payload, and the completeness check does not count it |

## In scope

### 1. Disclosure completeness as a named check
One function, one place: given a course, return the list of 8.01 items (by
number and name) that are missing or unusable. An item is unusable, not just
missing, when its source refuses — a stale 005 credit result fails item 3
even though a number exists. Item 11 is excluded while `may_claim_registry`
is false. Items 8–10 fail when the underlying policy has no current
published version.

### 2. Publish gate
Publishing a course runs the check and refuses with the itemized list when
anything fails. Same 422 `{"errors": [...]}` shape as everywhere else, one
error per missing item, each naming the item number. Unpublishing is
untouched. A course already published that would now fail (possible only in
dev; production starts empty) is flagged in the admin course view, not
auto-unpublished — silent state changes are worse than a visible warning.

### 3. Registration-and-attendance policy (item 8, 8.01.1)
8.01.1 requires registration and attendance policies to be formalized,
published, and available, alongside refund/cancellation and complaint
resolution. **First, look at what 011 actually built.** If 011's policy set
already includes a registration/attendance policy type, use it. If it does
not, add it as a new policy type through 011's existing append-only
effective-dated mechanism — do not invent a parallel storage. The site-open
gate's "all policies published" condition then includes it automatically if
the gate iterates policy types, or must be updated if it enumerates them;
check which, and say which in the changelog.

### 4. Public payload
`GET /api/v1/courses` (catalog: published courses only) and
`GET /api/v1/courses/{code}` (detail) carry the full disclosure. 004 built
early versions of these; bring them to the final shape:
- Detail payload has a named field for every applicable 8.01 item —
  a key-set test asserts their presence, the exact inverse of 015's
  no-field-for-course-facts test.
- Items 9 and 10 are links to the policy pages plus the effective date of
  the current version, not inlined policy text.
- Item 11: while `may_claim_registry` is false, the string "National
  Registry" appears nowhere in either payload (same test pattern as 003
  and 015).
- The 4.01 "most recent revision or review date," fed by 008's sign-off
  date, appears on the detail payload. This closes the ROADMAP improvement
  note; remove the note when it ships.
- Credit is displayed as 005 stored it (rounded per 7.01); the payload
  refuses to render a course whose credit is stale — that course fails the
  publish gate anyway.

### 5. Site-mode behavior
- `coming_soon`: both routes 404 anonymously, unchanged. They are **not**
  added to `INTENTIONALLY_PUBLIC`; the 015 router-walk test must keep
  passing without modification to its allowlist beyond what 015 put there.
  Admin preview of the disclosure page works through the existing hidden
  login.
- `open`: catalog and detail are public; the root path renders the catalog
  (015's SiteGate already stops serving the landing page at open — verify,
  don't assume, since the catch-all currently falls through to it).
- Extend the site-open gate: `coming_soon → open` now also refuses when no
  published course passes the disclosure check. Opening onto an empty or
  non-compliant catalog is opening onto nothing. The refusal message lists
  what's missing, same as the 011 policies refusal.

### 6. Frontend
- `/courses` — catalog of published courses: title, field of study,
  recommended credit, level, one-line description. No prices (018's
  problem), no register button (017's problem). The card links to detail.
- `/courses/:code` — the disclosure page, single column, the eleven items
  in a stable order with the item-8/9/10 policy links and the 4.01
  revision date. A visibly reserved space where registration will go, with
  no dead button.
- Both server-driven from the payloads above; the frontend renders what the
  API sends and adds no course fact of its own.

### 7. Docs and tests
- COMPLIANCE.md: rewrite the 8.01 row from "deliberately not satisfied" to
  satisfied-by-design, citing the completeness check and publish gate; add
  8.01.2 (prerequisites language) and the 4.01 revision-date row; update
  8.01.1 to note the registration/attendance policy joining the published
  set.
- Tests: completeness check item-by-item (each item independently missing →
  named error); publish gate refusal and success; payload key-set; Registry
  absence; mode matrix for both routes; open-gate refusal with zero
  compliant courses; 015's router walk untouched and green.

## Out of scope
- Self-registration and email verification (017), Stripe and prices (018),
  certificate delivery/verification (019), per-jurisdiction credit (020),
  invitations (021).
- The internal-training variant of 8.01 — superCPE's courses are developed
  for sale; do not build the shorter list.
- 8.01.3 group-program credit communication — self study only.
- Any change to what the coming-soon page shows. 015 is done; this feature
  replaces it only by virtue of the mode flip.

## Acceptance
1. A course missing any single applicable item cannot be published; the
   422 names the item by its 8.01 number.
2. With `may_claim_registry` false, publish succeeds without item 11 and
   "National Registry" appears nowhere in either public payload.
3. In `coming_soon`, both routes 404 anonymously and the 015 router-walk
   test passes with its allowlist unchanged.
4. Flipping to `open` (test env) makes the catalog the root page, the
   landing routes 404, and the detail page renders all applicable items
   including the three policy links and the 4.01 date.
5. The open gate refuses `coming_soon → open` when no published course
   passes the check, with an itemized message.
6. The registration/attendance policy exists as a published, versioned
   policy reachable from the course page.
7. Full suite green; changelog entry written, opening with the line that
   closes 015's stale known-gap paragraph (production reached `b0b8850`
   healthy on 2026-08-30; acceptance 6–7 completed — with the date Dane
   actually did the browser check).

## Notes for Claude Code
- Read 8.01, 8.01.1, 8.01.2, 4.01, and 7.01 from the uploaded 2026
  Standards before writing the completeness check; the item list in this
  spec was transcribed from the Standard but the code comments should cite
  the Standard, not this file.
- ROADMAP: record 016 as built-ahead-of-ship (Phase C feature, Phase B
  build), and remove the 4.01 improvement note when the date renders.
