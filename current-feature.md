# Current Feature

## Feature 021, Waiting-list invitations

## Goal
Everyone who signed the coming-soon waiting list gets the one email they
were promised: the site is open, here is where to register. One
invitation per entry, ever; sent by an explicit admin action that only
exists once the site is `open`; recorded per row with 019's
flag-plus-human-button pattern and no retry machinery. This is the last
Phase C code feature — it also writes the opening-day runbook that
sequences everything the flip needs.

## Read before building
015's waiting list (the soft delete, the `source` column, the
one-message email-use statement shown on the signup form — the exact
promise this feature is keeping), 017's email service, and 019's
delivery-status pattern. Reuse all three shapes; invent none.

## In scope

### 1. Invitation state on the waiting list
- `invited_at` (nullable) and `invitation_status`
  (`sent`/`failed`, nullable) on `waiting_list`. An entry is
  **invitable** when active (not removed) and never successfully
  invited. Migration; docstring unchanged — still not CPE records.

### 2. The send
- `POST /api/v1/admin/waiting-list/invitations` — guarded, logged.
  **Refuses while `site_mode` is `coming_soon`** with a message saying
  why: inviting people to a gated site would 404 in their faces, and
  keeping the action impossible until open means the flip can be
  rehearsed without a mass email riding on it. The flip itself never
  triggers sends — this button is deliberately separate.
- Sends sequentially to every invitable entry through the 017 service
  (kind `invitation`), writing `sent`/`failed` + `invited_at` per row
  as it goes; one failure doesn't stop the run. Returns a summary
  (attempted / sent / failed / skipped-already-invited).
- **Idempotent by construction**: re-running skips every `sent` row, so
  the button is safe to press after a partial failure — it becomes the
  retry for `failed` rows only. A per-row Resend also exists for
  symmetry with 019, but the batch button re-run is the expected path.
- Removed entries are never invited, including entries removed after a
  failed attempt.

### 3. The email
- One short message: superCPE is open, one plain sentence naming the
  ASC 842 practical-expedients course, a link to the register page and
  a link to the course page — **no credit figure, no field of study,
  no level, no price, no claims**: the course page carries the full
  8.01 disclosure; the email carries a link to it. Same restraint as
  the 015 landing page, same reasoning.
- A closing line keeping the 015 promise explicit: they asked to be
  told once, this is that one email, superCPE will not email them
  again (registering makes them a participant, which is a different
  relationship with its own transactional email).
- No mention of the National Registry in the template at all,
  claimable or not — the site says what may be said; the email needs
  no conditional. A test pins "National Registry" absent from the
  rendered invitation.
- No unsubscribe machinery: there is no subscription — the never-again
  line is the truth that makes that so, and removal before the send
  remains the existing admin action.

### 4. Admin surface
- `/admin/waiting-list` gains an Invitations panel: counts (active /
  invited / failed / invitable), the Send button behind a confirm
  dialog that repeats the refusal rule and the count about to be
  emailed, an invitation-status column on the table, and per-row
  Resend on `failed`. CSV export gains the two new columns.

### 5. Opening-day runbook
- OPERATIONS.md "Opening day (021)": the ordered checklist —
  1) 014 complete: course ingested on production, real reviewer
     sign-off recorded, published (priced, fully disclosing);
  2) policies published (011);
  3) SMTP configured and proven by the admin test-send (017), DNS
     SPF/DKIM in place;
  4) Stripe configured, webhook registered, test-mode walkthrough done
     (018);
  5) jurisdiction rows verified as far as intended (020, optional);
  6) `launch_findings` empty — the gate agrees;
  7) the flip (open closes permanently);
  8) smoke test: register a real account, buy the course in live mode,
     confirm the enrollment, refund yourself per the refund runbook if
     desired;
  9) **then** press Send invitations;
  10) watch the failed column; per-row resend as needed.
  Cross-reference each step to its feature's OPERATIONS section rather
  than restating procedures.

### 6. Tests and docs
- Refusal in `coming_soon`; full run at `open` (test env) writes one
  `sent` per active entry with one outbound `invitation` email each;
  re-run attempts zero; a forced per-row failure marks `failed`
  without stopping the run, and both the re-run and the per-row Resend
  recover it; removed entries untouched; the Registry-absence pin;
  router walks green, allowlists untouched.
- COMPLIANCE.md: extend the 8.01 no-descriptive-material row — the
  invitation follows the landing page's rule (link, don't restate) now
  that full disclosure exists to link to.
- Changelog entry notes Phase C code complete: what remains is 014,
  the Registry application, the ops checklist, and the flip.

## Out of scope
- Any second email, newsletter, campaign, or unsubscribe
  infrastructure — the never-again line is load-bearing.
- Discounts or early-signup perks (`source` stays an analytics
  distinction; coupons stayed out of 018).
- Automatic sending on the flip (deliberate, see above).
- Retry daemons — the idempotent re-run is the retry.

## Acceptance
1. In `coming_soon`, the send endpoint refuses and the admin button
   explains; nothing is emailed.
2. Flipped open in the test env: one run sends exactly one invitation
   per active entry, the summary adds up, and the console backend log
   matches row statuses.
3. A second run attempts zero; after a forced failure, the re-run (or
   row Resend) sends only to the failed row.
4. The rendered email contains the two links, no course facts beyond
   the naming sentence, no "National Registry", and the never-again
   line.
5. Removed entries — before the run or after a failure — are never
   emailed; the CSV carries the new columns.
6. Full suite green; changelog entry written, closing Phase C code.

## Notes for Claude Code
- Sequential send with a per-row commit (or savepoint) so a crash
  mid-run loses nothing already recorded — the re-run picks up where
  it died.
- ROADMAP: mark 021 built ahead of ship and Phase C code complete;
  the remaining lines are 014, the Registry application, and the flip.
