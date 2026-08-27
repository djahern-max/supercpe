# Current Feature

## Feature 003, Sponsor identity record

## Goal
superCPE knows who the sponsor is: the facts that Section 9.01 requires on
every certificate and that 9.01.1 makes the sponsor responsible for. They are
stored once, edited in the admin, and exposed through a `missing_fields`
check that later features use to refuse to publish a course or issue a
certificate from an incomplete or unregistered profile.

## In scope
- `sponsor_profile` singleton table
- State registrations as rows, not a text blob
- Registry status, and the rule that nothing may claim Registry membership
  until it is true
- `GET`/`PUT` admin endpoints, and a public read of the non-sensitive subset
- `missing_fields` as a derived property
- Admin edit page
- The two constants 9.01 fixes in words

## Out of scope
- Certificates. Feature 010 reads this record; nothing renders one yet.
- Refund, cancellation, and complaint policies (8.01.1). Site-wide pages,
  feature 011 alongside the audit bundle.
- Multiple sponsors. A second row is a state this application has no meaning
  for; the CHECK constraint below says so.
- Real auth. Still `X-Admin-Token` from 002.

## Locators
Read 9.01, 9.01.1, and 9.02 in the Standards PDF before starting. Take
COMPLIANCE.md's Requirement column from the PDF's words. This feature is
built against 9.01 items 1, 8, 9, 10, 11 and against 9.01.1's sentence that
the entity named on the certificate is responsible for awarding the credit.

## Registry status, read this before the data model
NASBA's National Registry of CPE Sponsors is a membership. A sponsor that has
not been accepted does not have a sponsor ID and may not describe itself as a
Registry sponsor. superCPE is not on the Registry today.

So the profile carries `registry_status` with two values, `not_registered`
and `registered`, and the rule is: when `not_registered`, `national_registry_id`
must be empty, and no response, page, or document may include the words
"National Registry" or a sponsor ID. This feature enforces the first half (a
CHECK constraint plus validation) and gives later features the second half as
a single boolean to read: `profile.may_claim_registry`.

State boards are separate. Some require their own sponsor registration and
number (9.01 item 9); some accept Registry sponsors without one; some require
nothing for self study. superCPE does not encode which states require what.
It stores whatever registrations the sponsor actually holds, and certificates
will print them.

## Data model
Table `sponsor_profile`:
- id: integer PK, CHECK `id = 1`
- name: string, not null, default ''
- legal_name: string, not null, default ''. The entity 9.01.1 holds
  responsible; may equal `name`.
- registry_status: string, not null, default 'not_registered',
  CHECK in ('not_registered', 'registered')
- national_registry_id: string, not null, default ''
- CHECK: `registry_status = 'registered' OR national_registry_id = ''`
- website, contact_email, contact_phone, address: string, not null, default ''
- other_certificate_statements: text, not null, default ''. 9.01 item 11,
  free text, one statement per line. Empty is normal.
- updated_at: timezone-aware, server default, updated on write

Table `sponsor_state_registrations`:
- id: integer PK
- state: string(2), not null, uppercase USPS code
- registration_number: string, not null
- notes: text, not null, default ''
- unique on `state`

The singleton row is created by the migration itself with defaults, so the
application never has to handle "no profile yet". `missing_fields` handles
"profile is blank".

## Constants
`app/constants/certificate.py`:
- `TIME_STATEMENT = "CPE credits have been granted based on a 50-minute hour."`
  9.01 item 10, cited in a comment. Not editable; NASBA fixes the wording's
  substance, and a sponsor has no reason to vary it.
- `CERTIFICATE_SPONSOR_FIELDS = ["name", "national_registry_id"]`. The
  sponsor-level fields a certificate cannot be issued without. Item 9 is
  conditional on the state, so state registrations are not in this list.

## `missing_fields`
A method on the model, `missing_fields() -> list[str]`, returning the names
of every field in `CERTIFICATE_SPONSOR_FIELDS` that is blank, plus
`"registry_status"` if the status is `not_registered`. Empty list means a
certificate may name this sponsor. A blank profile returns all three, not a
500 — write the test for that first.

`may_claim_registry` is a property: `registry_status == "registered" and
national_registry_id != ""`.

## Backend tasks
1. The two models, then `alembic revision --autogenerate -m "create sponsor
   profile"`. Hand-add the three CHECK constraints and an `op.execute` that
   inserts the id=1 row with defaults. Verify `downgrade -1` removes both
   tables and `upgrade head` recreates the row.
2. `app/constants/certificate.py` as above.
3. `app/services/sponsor.py`: `get_profile(db)` (always returns the row),
   `update_profile(db, data)`, `set_state_registrations(db, rows)` replacing
   the full set atomically. Updating with `registry_status = 'registered'`
   and a blank id, or `not_registered` and a non-blank id, is refused with a
   422 naming the rule before the CHECK ever fires.
4. Schemas: `SponsorProfileAdmin` (everything, plus `missing_fields` and
   `may_claim_registry` as read-only fields), `SponsorProfileUpdate`,
   `StateRegistration`, and `SponsorProfilePublic` carrying only `name`,
   `website`, and, when `may_claim_registry` is true, `national_registry_id`.
   The public schema never carries the id when the status is not registered;
   test that explicitly.
5. Routers: `GET`/`PUT /api/v1/admin/sponsor` and
   `PUT /api/v1/admin/sponsor/state-registrations` behind `require_admin`;
   `GET /api/v1/sponsor` public.
6. Tests, `tests/test_sponsor.py`:
   - fresh database has exactly one profile row with all three missing fields
   - PUT updates and returns `missing_fields` shrinking accordingly
   - registered with blank id → 422; not_registered with an id → 422
   - public endpoint omits `national_registry_id` when not registered and
     includes it when registered
   - state registrations replace as a set; lowercase state code is uppercased;
     duplicate state in one payload → 422
   - a second profile row cannot be inserted (CHECK on id)
   - `missing_fields()` on a blank profile does not raise

## Frontend tasks
1. `src/api/sponsor.js`: `getSponsor(token)`, `updateSponsor(token, data)`,
   `setStateRegistrations(token, rows)`.
2. `src/pages/AdminSponsor/` at `/admin/sponsor`, reusing 002's in-memory
   token handling. One form for the profile fields; a small editable table
   for state registrations (add row, remove row, save as a set).
3. A status panel at the top of the page: "Certificates can be issued" when
   `missing_fields` is empty, otherwise the list of what is missing, in plain
   language ("Sponsor name is blank", "Not yet on the National Registry").
   This is the panel a person checks before launch.
4. The registry fields behave together: selecting `not_registered` clears and
   disables the ID field; selecting `registered` enables it and marks it
   required.
5. Add `/admin/sponsor` to whatever admin navigation exists from 002.
6. Move the `.env.example` `ADMIN_TOKEN` comment, if any, to say the token
   protects sponsor and package admin. Trivial, but the file should be true.

## COMPLIANCE.md
Rows for 9.01 (items 1, 8, 9, 10, 11 as one row or five, whichever reads
better), 9.01.1, and 9.02's five-year retention as a row whose Gap column
says the period is not yet recorded anywhere in code; feature 011 adds the
constant. The 9.01 item 8 Gap column states the Registry-status rule and
that superCPE is not registered.

## Acceptance
- `alembic upgrade head` on a fresh database yields one sponsor row
- `pytest` passes; `test_sponsor.py` covers the list above
- Admin page: blank profile shows three missing items; filling name and
  setting registered with an ID clears them; the public endpoint reflects it
- Toggling back to `not_registered` clears the ID and the public endpoint
  stops returning it
- Adding two state registrations and reloading shows both; removing one and
  saving removes it

## When done
Append the 003 entry. Under Decisions: singleton by CHECK not convention;
state registrations as rows; the registry-status rule and why. Under Known
gaps: not registered; retention period not yet a constant; the "may not
claim Registry" rule is enforced on this feature's own responses only, and
every later feature that renders sponsor facts must read
`may_claim_registry`. Then stop.
