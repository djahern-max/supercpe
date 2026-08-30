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

Phase A is code-complete (012 built and tested 2026-08-29); it closes for
good when 012's first deployment and restore drill are executed and its
changelog entry lands.

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

- 013 Coming-soon landing page and waiting list table, with CSV export
- 014 Hidden login and tester accounts; site mode switch in the admin

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

- 015 Public landing page, catalog, course pages with full 8.01 disclosure
- 016 Self-registration and email verification
- 017 Stripe checkout; payment success creates the enrollment (010) and
  starts the one-year clock; refunds follow the 8.01.1 policy page
- 018 Certificate delivery by email and a public verification page
- 019 Per-jurisdiction credit policy: rounding increment (7.01) and
  non-technical caps, read from a table the admin maintains
- 020 Waiting-list invitation emails

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
- The 4.01 "most recent revision or review date" shown on the course page,
  fed by 008's sign-off date.
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
  participant is a new enrollment with its own year (and, once 017 exists, a
  goodwill re-enrollment at no charge is a sponsor policy, not a Standards
  question).
- Off-provider backup copies: 012 keeps snapshots and nightly dumps at
  DigitalOcean only, so a provider-level failure (account lockout,
  regional loss) could take the originals and every backup together —
  which 9.02 arguably wants covered. A second bucket at a different
  provider, or a periodic download to a machine the sponsor controls,
  would close it.
