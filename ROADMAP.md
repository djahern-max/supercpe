# Roadmap

Where superCPE is going, in phases. `current-feature.md` is always one feature
from this list. Features may be renumbered; phases will not be reordered.

superCPE is a rebuild, not a port. abacadaba (../abacadaba) was the rough draft
that discovered what the Standards require; superCPE is shaped around those
requirements from the start rather than retrofitting them. When a feature here
does something abacadaba also did, do it the way the Standards read, not the
way abacadaba did it. Five structural differences are deliberate:

1. Review questions are asked inside the video at `after_block`, not on a quiz
   page afterward (5.01.2.1, "throughout the program").
2. Enrollment is the record everything hangs off, and it carries the
   expiration date from day one (9.02.2(3)). Payment later becomes the event
   that creates it; nothing downstream changes.
3. Content review sign-off is a dated record by a named, licensed reviewer,
   and a course cannot publish without one (4.02, 9.02.2(4)).
4. Every certificate-bearing fact is snapshotted at completion; nothing a
   participant holds can be rewritten by a later edit.
5. The 9.02.2 documentation set is an exportable bundle per course, built up
   feature by feature, not assembled at audit time.

## Phase A — Build, local only
Everything runs on the developer's machine. No public surface.

- 001 Walking skeleton ✓
- 002 Course package ingest ✓
- 003 Sponsor identity record
- 004 Courses assembled from lesson packages; `course_code` and `position`
  formalized in the contract; unattached-package deletion
- 005 Credit measurement (7.02.6/7.02.7, 7.01 rounding, inputs stored)
- 006 Participant video player with in-video review questions (5.01.2.x)
- 007 Qualified assessment (6.01.2: floors, passing score, no forced-choice,
  feedback, retake policy)
- 008 Content review sign-off and publish gate (4.01.1, 4.02, 9.02.2(4))
- 009 Accounts, roles, sessions. Roles: participant, reviewer, admin.
  Replaces the shared token. Includes **site mode** (see Phase B).
- 010 Enrollment with expiration, completion record, certificate with
  snapshot (9.01, 9.02.2(1), 9.02.2(3))
- 011 Program evaluation (4.04), policies pages (8.01.1), retention
  constant, and the per-course audit bundle export (9.02)
- 012 Spaces storage implementation, production config, deployment to
  superCPE.com. **Checklist before deploying** (from 010): the dev
  database's ASC842-PCX was published on a test review by a fictitious
  reviewer; unpublish, delete the fictitious SME and their review, and
  re-review with the real second CPA before anything ships.
  **Storage key prefixes in use** (from 011) — the Spaces implementation
  and its backup policy must cover all three: `packages/` (lesson videos),
  `certificates/` (rendered PDFs), `audits/` (bundle zips). All three are
  write-once: nothing in code overwrites or deletes an existing key under
  any of them.

Phase A closed 2026-08-30: 012's first deployment, rollback exercise, and
restore drill were all executed and its changelog entry landed.

## Phase B — Deployed, closed
superCPE.com is live but the public sees a coming-soon page.

**Site mode** is a setting on the sponsor profile, not an environment
variable, so it can be flipped without a deploy and the flip is logged:

- `coming_soon`: every public route renders the landing page with a waiting
  list form (name, email, state of licensure, optional firm). `/login` still
  works and is not linked from anywhere; staff and testers sign in there and
  see the full participant application. Nothing behind login mentions the
  Registry (003's `may_claim_registry` stays false).
- `open`: the real landing page, self-registration, catalog, purchase.

- 013 Durability of retained records: bucket object versioning with one
  lifecycle rule, boot/health enforcement, off-site mirror (built
  2026-08-30; the versioning setup run and the bucket-layer drill are
  014 prerequisites; the mirror is dormant — see the improvement note)
- 014 ASC842-PCX re-ingest on production with the real second CPA's
  review; production catches up to main (bucket-setup, deploy of 013)
- 015 Coming-soon landing page and waiting list table, with CSV export
  (shipped 2026-08-30, **before 014**: 014 is deferred, not cancelled —
  blocked on narration audio for lessons 2–4, a second licensed CPA to
  sign the 4.02 review, and a legal entity for the sponsor profile,
  none of which 015 needs; 015 is what makes the live site do
  something while they resolve. 014 keeps its number.)

(The pre-renumbering Phase B list had the landing page as 013 and
"hidden login and tester accounts; site mode switch in the admin" as
014. The latter was absorbed before Phase B began: 009 built the
unlinked `/login` and the admin site-mode switch with its change log,
and 009/010 give the admin account creation and enrollment-by-email,
which is all a tester account is.)

Phase B backlog from 012's first deploy (2026-08-30):

- Ops, no code: rotate the `doadmin` cluster password and the starter
  admin password (both were exposed in a chat transcript during setup);
  apply the droplet's pending OS security updates (109 pending, 90
  security, as of the deploy).
- Enable Spaces object versioning with a lifecycle rule expiring
  noncurrent versions under `backups/` only (see the 2026-08-30
  correction entry in COMPLIANCE.md for why it is its own feature).

This is the state in which the NASBA Registry application is prepared. The
application needs a sample course, the credit calculation, the review
record, the policies, and the certificate — all of which 004–011 produce.
The audit bundle from 011 is most of the application packet.

## Phase C — Registered, open
After NASBA acceptance: set `registry_status = registered` with the sponsor
ID, flip site mode to `open`.

- 016 Public landing page, catalog, course pages with full 8.01 disclosure
  (built 2026-08-31, ahead of ship: a Phase C feature finished and tested
  during Phase B behind the 009 gate, so it is live the moment site mode
  flips to `open` — which the gate now also refuses until a published
  course discloses completely)
- 017 Self-registration and email verification (built 2026-08-31, ahead
  of ship like 016: every public route 404s in `coming_soon`, and the
  open gate now also refuses until the email backend is smtp with
  complete settings)
- 018 Stripe checkout; payment success creates the enrollment (010) and
  starts the one-year clock; refunds follow the 8.01.1 policy page
  (built 2026-08-31, ahead of ship like 016/017: every public route
  404s in `coming_soon`, and the open gate now also refuses until the
  three STRIPE_* settings are complete; the operator's Stripe-account
  setup and test-mode walkthrough are in OPERATIONS.md "Payments (018)")
- 019 Certificate delivery by email and a public verification page
  (built 2026-08-31, ahead of ship like 016–018: the verification route
  404s anonymously in `coming_soon` and delivery flows through 017's
  email backend, so both go live with the flip and need no new gate)
- 020 Per-jurisdiction credit policy: rounding increment (7.01) and
  non-technical caps, read from a table the admin maintains
  (built 2026-08-31, ahead of ship like 016–019: the hint endpoint 404s
  anonymously in `coming_soon` and the policy table ships empty, so
  nothing shows anywhere until Dane verifies rows — OPERATIONS.md
  "Jurisdiction policies (020)")
- 021 Waiting-list invitation emails
  (built 2026-08-31, ahead of ship like 016–020: the send action refuses
  while `coming_soon`, so nothing can be emailed before the flip; it is
  step 9 of OPERATIONS.md "Opening day (021)", after the smoke test)
- 022 Site identity and link previews — favicon, OG card, robots.txt,
  mode-aware sitemap — the first post-021 feature demanded by reality
  rather than the Standards: links to the site should look like the site,
  and indexing should start while coming_soon so the domain has standing
  by opening day (built 2026-08-31; metadata only, no analytics —
  OPERATIONS.md "Site identity (022)")

**Phase C code is complete.** What remains is not code: 014 (the course
ingested on production with the real reviewer's sign-off), the NASBA
Registry application, and the flip itself — sequenced in OPERATIONS.md
"Opening day (021)".

(Phase C shifted by one on 2026-08-30 when Phase B was renumbered;
feature numbers cited inside past CHANGELOG entries are history and
refer to the numbering of their day.)

## Not planned
- Group or blended learning programs. Self study only until there is a
  reason.
- Pilot testing (method 1). Word count formula only.
- Multiple sponsors.
- Adaptive or nano learning.

## Improvement notes
Anything discovered mid-feature that would make superCPE better but is out
of scope goes here as a one-liner, so it is not lost and not built early.

- Participant-facing captions/transcript toggle on the player for
  accessibility; must be labelled as the narration, not as reading material
  (7.02.5).
- When attach refuses a taken manifest position, the error could suggest the
  lowest free position instead of making the admin work it out.
- `update_version` on a course's only lesson compares the new package's
  derived fields against values that came from the lesson being replaced, so
  a re-export that rewords prerequisites can only be swapped in by
  detach-then-attach; the agreement check could exclude the lesson being
  updated.
- 4.05.3 items 2–3: the course package should carry a glossary
  (`manifest.glossary[]`, term/definition/source) and superCPE should
  render it with a term search — a contract change coordinated through
  `docs/course-package.md` and a video-tool feature to author it from the
  sources folder.
- The Standards' effective-date paragraph (self study programs first
  published on or after March 1, 2027 must comply with the 2026 edition;
  existing programs by November 1, 2028) is deliberately recorded nowhere
  in code (011's conclusion): superCPE is built to the 2026 Standards
  uniformly from the start, so the transition dates gate no behavior — a
  constant would exist only to never be read. If a pre-2026-Standards
  program ever needed hosting, that would be a new requirement, not a
  flag flip.
- Admin extension of an enrollment's expiry: deliberately not built (010).
  9.02.2(3) reads "no longer than one year from the date of purchase or
  enrollment" — a cap anchored to the original enrollment, not a clock that
  can be reset — so an extension past that year would put the qualified
  assessment outside the window the Standard fixes. The remedy for a lapsed
  participant is a new enrollment with its own year (and, once Stripe
  checkout (018) exists, a goodwill re-enrollment at no charge is a sponsor
  policy, not a Standards question).
- Off-provider backup copies: 012 keeps snapshots and nightly dumps at
  DigitalOcean only, so a provider-level failure (account lockout,
  regional loss) could take the originals and every backup together —
  which 9.02 arguably wants covered. A second bucket at a different
  provider, or a periodic download to a machine the sponsor controls,
  would close it.
- The off-provider note above is closed by 013: nightly dumps,
  `certificates/`, and `audits/` mirror to a second S3-compatible bucket
  at a different provider, and `/health` reports
  `last_offsite_backup_at`.
- `packages/` has no off-site copy (013 decision): videos are large and
  every exported zip also exists in video-tool's `dist/` on the machine
  that produced it. If video-tool's machine and DigitalOcean were both
  lost, the lesson videos would be too; mirroring `packages/` (or an
  archival copy of video-tool's `dist/`) would close it.
- 2026-08-30: the 013 mirror is built but dormant — the operator chose
  not to set up a second-provider bucket at this time, so `OFFSITE_*` is
  unset and the off-provider exposure two notes up stands until it is.
  Turning it on is the five `OFFSITE_*` values in the server `.env` plus
  one `backup.sh` run; no code. (COMPLIANCE.md carries the matching
  2026-08-30 correction row.)
- Sales tax on course sales (018): checkout charges the bare price with
  no tax handling. Stripe Tax can compute and collect it on the same
  hosted Checkout page (one parameter plus dashboard registration) if
  and where selling CPE courses turns out to be taxable — an
  accountant's question before a code change.
- Password reset (017a?): 002 built no reset for the hidden login and 017
  deliberately did not ride it in. The 017 token machinery
  (`email_verification_tokens`, hashed single-use tokens, supersede-on-
  resend) was written so a reset can reuse the shape unchanged; it is its
  own small feature.
- Per-course OG link previews (022): the OG tags are static and
  site-wide because the frontend is a SPA and scrapers run no
  JavaScript. A pasted course URL previews with the site-wide card, not
  the course title. Fixing it means SSR or edge-injection of per-route
  meta tags (and per-course cards would then have to carry the full 8.01
  question all over again) — its own feature if it ever matters.
- The 4.05.3 items 2–3 note above (glossary in the package contract) is
  absorbed and extended by 023: glossary plus keyword search, both
  publish-gated, for text-first packages. Closed 2026-09-01 by 023's
  Part B; the video-tool half of it is Part C.
- The 4.02 attestation 023 shows the reviewer is not stored on the
  review it belongs to (023's spec said no schema change). A future
  reader infers the wording from `ATTESTATION_VERSION` and the sign-off
  date; storing the signed text on `course_reviews` would be better
  evidence and is its own small feature.
- A text lesson carries a `lesson_progress` row shaped for video
  (`furthest_seconds`), which means nothing for a study guide. Nothing
  reads it and the participant page shows "Study guide" instead of a
  timecode; removing it would touch the 010 progress contract. 

## Phase D — Text-first catalog
Decided 2026-09-01, during the first end-to-end authoring run
(first-course-walkthrough.md), by the operator as a user. Full rationale
and integrity lines: the "Text-first courses" entry in this repo's
docs/decisions/ (or wherever the long-form pivot record lands).

The short version: under Method 2, 50 minutes of produced video buys 1.0
credit and ~9,000 words of instructional text buys the same (7.02.6), and
the self-study market buys credits per hour of effort. Video-first cannot
produce a competitive catalog. The primary format becomes a study guide
(words ÷ 180) with short supplemental videos that are genuinely additional
learning (7.02.7) and review questions placed between sections (5.01.2.1,
"throughout the program" — the same principle as structural difference 1,
generalized from video blocks to text sections). ASC842-PCX is
reclassified as the pipeline validator, not the flagship.

Nothing in Phases A–C changes: Method 2 only, all gates, snapshots, and
retention rules carry over. The 7.02.5 exclusions (glossary, appendixes,
front matter out of the word count) are enforced structurally at
ingestion, and word_count for text packages is computed from the shipped
text, not trusted from the manifest (closes the 005 trust row for the
format that matters).

- 023 Text-first course packages: contract change in
  docs/course-package.md (`kind: text`, sections with roles, supplemental
  media), computed word count, participant reader with section-gated
  review questions, keyword search and glossary (4.05.3 items 2–3 become
  publish-gate refusals), reviewer attestation extended to 7.02.7/7.02.5
  scope. Spec: current-feature.md.
  (Parts A and B built 2026-09-01 against a hand-made fixture package.
  **Part C — video-tool authoring and export — is not built**, and until
  it is, the only text package that exists is that fixture; copying
  `docs/course-package.md` into video-tool identically is the first step
  of that session. The open question above about the forward-seek lock is
  decided: relaxed for supplemental clips, kept for the video-only
  player, recorded in the decision doc and the 023 entry.)
- 024 First text-first course authored and ingested (topic TBD; ASC 842
  expansion is the candidate — research and videos exist).