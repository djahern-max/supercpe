# Feature 015 — Coming-soon landing page and waiting list

## Note on ordering

ROADMAP lists 014 (ASC842-PCX re-ingest on production with the real second
CPA's review) before this. 014 is **deferred, not cancelled**: it is blocked
on three things no code can produce — narration audio for lessons 2–4
(ElevenLabs spend, then render and export in video-tool), a second licensed
CPA willing to sign the 4.02 review, and a legal entity to fill the sponsor
profile. None of those blocks this feature, and this feature is what makes
the live site do something while they resolve.

Numbers are not being reshuffled again. 014 keeps its number and gets built
when its prerequisites land. Add one line to ROADMAP's Phase B list recording
that 015 shipped first and why.

Prerequisite: 014a is complete and production is healthy at the 014a sha —
`/health` all ok including `bucket_versioning`, preflight passing in the
deploy output.

## Why this feature exists

superCPE.com has been live in `coming_soon` mode since 2026-08-30 and every
public route answers 404. That was the correct 009 behavior for a site with
nothing to show, but it is now the only thing standing between the domain and
its first useful job: collecting the names of CPAs who want the course when it
opens.

The compliance shape of this page is unusual and worth stating up front,
because the instinct to "put the course details on the landing page" is
exactly wrong here. Section 8's eleven-item disclosure (8.01) attaches to
descriptive materials for courses developed for sale, and 8.01.1 names
websites explicitly as a channel where significant features must be disclosed
in advance. superCPE cannot satisfy that list yet — there is no published
credit figure on production, no policies, no sponsor legal name, and item 11
(the official NASBA sponsor statement) is unavailable because superCPE is not
a Registry sponsor. **A page that discloses some of the eleven items is worse
than one that discloses none**, because partial disclosure looks like
descriptive material and is not. So this page announces that something is
coming and collects an email. Full 8.01 disclosure is 016's job, and 016 does
not ship until the facts behind all eleven items exist.

## Scope

### 1. `waiting_list` table

Migration adds one table. Columns: `id`, `name`, `email`, `state` (state of
licensure), `firm` (nullable), `created_at`, `removed_at` (nullable),
`removed_reason` (nullable), `source` (default `'coming_soon'`, so 021 can
tell an early signup from a later one).

Email is stored lowercased and trimmed with a unique index. `state` is a
two-letter US jurisdiction code validated against a constant list in
`app/constants/jurisdictions.py` — the same list 020 will need for
per-jurisdiction credit policy, so put it somewhere 020 can reuse it rather
than inline in a validator.

**These rows are not CPE records.** Say so in the model's docstring. They are
not participants, no enrollment exists, and `RETENTION_YEARS` does not apply
to them. `removed_at` is a soft delete so that a request to be taken off the
list is honored immediately without deleting a row mid-migration; a removed
row is excluded from every count, listing, and export. This is deliberately
different from the 9.02 accounts rule, and the difference should be stated in
the docstring so nobody later "fixes" it for consistency.

### 2. Public endpoints, carved out of the 009 site gate

009's gate answers 404 on public routes while `site_mode` is `coming_soon`.
Two endpoints become explicit exceptions, allowed **only** in `coming_soon`:

- `GET /api/v1/landing` — returns what the page needs to render: the sponsor
  display name if set, `may_claim_registry` (003), and whether the policies
  pages are published. Nothing else. It must not return course facts, credit
  figures, objectives, or prices; there is no field on this response for them.
- `POST /api/v1/waiting-list` — `{name, email, state, firm?}`. Validation
  errors use the same 422 `{"errors": [...]}` shape as 002/003/004. A repeat
  email is a 200 with the same body as a first submission (idempotent; the
  row's `created_at` is not moved). A submission against a `removed_at` row
  clears the removal and re-adds.

Both routes must appear in 009's router-table walk test, marked as
intentionally public, so the test that catches an unguarded route does not
have to be weakened to accommodate them.

Spam controls, in this order of preference: a hidden honeypot field that must
be empty (rejected silently with a 200 so a bot learns nothing), and a Caddy
rate limit on `POST /api/v1/waiting-list` mirroring the login rule already in
`deploy/Caddyfile`. No CAPTCHA, no third-party service.

When `site_mode` is `open`, both routes 404. The waiting list stops accepting
entries the moment the real site opens; 021 mails the people already on it.

### 3. The landing page

Every unmatched public path in `coming_soon` mode serves this page instead of
404. `/login` is unchanged: it works, it is not linked from this page, and
nothing about it appears in the markup.

What the page may say:

- Who superCPE is, in plain language, and that it is self-study CPE for
  licensed CPAs.
- That a course on the ASC 842 private-company practical expedients is in
  preparation. A one-paragraph plain-language description is fine.
- That full program details — learning objectives, recommended credit and
  field of study, prerequisites, advance preparation, and the registration,
  refund, and complaint policies — will be published before registration
  opens. This sentence is the page's honest substitute for 8.01, and it
  should be there.
- The waiting-list form: name, email, state of licensure, firm (optional),
  and a clear statement of what the email will be used for (one message when
  the course opens; nothing else).

What the page must not say, enforced in code and in tests:

- Anything from the 8.01 eleven-item list stated as fact — no credit number,
  no field of study, no knowledge level, no prerequisites, no price.
- The words "National Registry", any sponsor ID, or the NASBA sponsor
  statement. The page reads `may_claim_registry` and renders that block only
  when true; since it is false, the block is absent. Add a test that fetches
  the rendered landing response and asserts the string "National Registry"
  does not appear while `may_claim_registry` is false. 003's known gap says
  every surface that renders sponsor facts must check this — this is the
  first public one.
- Anything implying the course can be purchased or registered for now.

Footer links to the 011 policies pages **if** they are published, since 8.01.1
wants registration, refund, and complaint policies formalized, published, and
available. On production they are not published yet, so the footer renders
without them; do not fake them.

Styling uses the existing CSS Modules setup. No new frontend dependency, no UI
kit, no analytics or third-party script of any kind.

### 4. Admin surface

`/admin/waiting-list`, admin role only: total count, a table (name, email,
state, firm, signed up), a search box filtering on name and email, and two
actions — Remove (sets `removed_at` with an optional reason) and
`GET /api/v1/admin/waiting-list/export.csv`.

The CSV is the deliverable that matters: header row, one row per active
entry, ISO-8601 timestamps, UTF-8. It is the file that will be handed to
whatever sends 021's invitations, and it is also the honest answer to "how
many people actually want this" while the Registry application is in flight.
It is not written to Spaces and not part of the 9.02 audit bundle — it is a
download, generated on request.

### 5. Documentation

- `COMPLIANCE.md`: an 8.01 row recording that the coming-soon page carries no
  descriptive material by design and that 016 owns the eleven-item
  disclosure; an 8.01.1 row noting the policies-footer behavior; and a row
  under 003's Registry-claim rule recording this as the first public surface
  that checks `may_claim_registry`.
- `docs/OPERATIONS.md`: a short section on the waiting list — where to see
  the count, how to export, and that flipping `site_mode` to `open` closes
  submissions permanently.
- `ROADMAP.md`: the one line about 014 being deferred, and 015 moved ahead.

## Explicitly out of scope

- Sending any email. No SMTP configuration, no provider, no templates. 021
  owns invitations; 017 owns verification.
- Self-registration, accounts for waiting-list entries, or any link between a
  waiting-list row and an `accounts` row. They are strangers until 017.
- The open-mode landing page, catalog, or course pages (016). This page is
  deleted or replaced when that ships; do not try to make it dual-purpose.
- Any change to `ensure_bucket_versioning`, the preflight gate, or anything
  else 014a settled.
- The 014 re-ingest, the sponsor profile, the second CPA's review, or
  publishing anything.

## Standards read before coding

Read these in `docs/2026-Statement-on-Standards-for-CPE-Programs.pdf`, not
from this summary:

- **8.01** — the eleven items required in advance for courses developed for
  sale. Read it to understand what this page is deliberately not doing.
- **8.01.1** — significant features disclosed in advance, websites named as a
  channel; registration, refund, and complaint policies formalized,
  published, and available.

## Acceptance

1. Full test suite passes locally; report the count (252 at the 013
   checkout, plus whatever 014a added).
2. Locally, with `site_mode = coming_soon`: an unmatched public path serves
   the landing page; `/login` still works and appears nowhere in the landing
   markup; a valid submission returns 200 and creates one row; the same email
   again returns 200 and creates no second row; a bad state code returns 422
   in the standard shape; the honeypot submission returns 200 and creates
   nothing.
3. With `site_mode = open`: both public endpoints 404.
4. The Registry-claim test passes — "National Registry" absent from the
   landing response while `may_claim_registry` is false.
5. Admin page lists entries, search filters, Remove hides the row from the
   list and from the CSV, and the CSV opens in a spreadsheet with correct
   headers.
6. Deployed to production via `deploy.sh` (preflight passes), then, on
   https://supercpe.com: the landing page renders over TLS, one real
   submission is made and appears in the admin table, and the CSV downloads.
   `/health` reports the new sha with all components ok.
7. Confirm by eye on the deployed page that no credit figure, price,
   prerequisite, or Registry language appears anywhere.

## When done

Append the 015 changelog entry in the CLAUDE.md format and stop. List
anything found but out of scope at the end of the response rather than
building it.
