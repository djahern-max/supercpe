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
  superCPE.com

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
