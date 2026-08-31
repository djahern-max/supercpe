# Current Feature

## Feature 019, Certificate delivery and public verification

## Goal
When a participant completes a course, the certificate reaches them by
email without them asking, and anyone they hand it to — a state board, an
employer — can confirm it is real on a public page. Delivery is a courtesy
layered on the record; the record is the snapshot the completion already
made, and nothing in this feature can make completion fail. Like 016–018,
**built now, ships at open**.

## Read before building
Read the existing certificate feature first: the completion-time snapshot,
the render, where the PDF lives in `certificates/` (a 9.02 record under
bucket versioning), and whatever participant-facing download already
exists. 019 adds delivery and verification around it; it does not touch
what the certificate says or when the snapshot is taken (standing
decision: at completion, not at render). Read 017's email service — the
`send` interface, the console/smtp backends, the `email_message` log —
because delivery goes through it, extended, not around it.

Then read 9.01 and 9.01.1 from the 2026 Standards before writing the
COMPLIANCE rows: the ≤60-day timeliness expectation and the sponsor's
role in issuing acceptable documentation are the two hooks this feature
hangs on. Cite what the Standard says, not this spec.

## In scope

### 1. Verification code on the certificate
- Every certificate row gains a high-entropy verification code
  (URL-safe, ≥128 bits, unique, generated at issuance). It is an
  identifier, not a secret credential — stored plainly, indexed.
- The rendered PDF gains one line near the sponsor block: "Verify this
  certificate at supercpe.com/certificates/verify — code: XXXX…". This
  is a template change; it applies to certificates issued from now on.
- Migration backfills codes for existing (dev-only) certificate rows so
  the verification page works for them, but **does not re-render their
  PDFs** — snapshots are immutable, and production starts empty so no
  real certificate will ever lack the printed line. Say this in the
  changelog.

### 2. Email delivery on completion
- On completion, after the snapshot and render succeed, send one email:
  kind `certificate`, the PDF attached, a sentence naming the course,
  credit, and completion date, and a link to the participant's
  certificates page. Attachment support is the one extension the 017
  email service needs (both backends; the `email_message` row records
  the attachment filename, still never a body).
- **Delivery failure cannot fail completion.** The send happens after
  the completion transaction commits (background task or
  post-commit hook — whatever fits the existing completion flow), and a
  failure is recorded, not raised: the certificate row gains
  `delivery_status` (`sent` / `failed` / `pending`) and
  `delivered_at`. The participant can always download from their
  account regardless — that path is what actually satisfies 9.01's
  timeliness; the email is how it satisfies it without being asked.
- Admin: a Resend action on the certificate (guarded, logged, updates
  delivery status), and failed deliveries surfaced on the admin
  certificates view. No automatic retry machinery — one loud flag and a
  human button; retries are a follow-up if reality demands them.

### 3. Public verification
- `GET /api/v1/certificates/verify/{code}` — public at `open`, 404
  anonymously in `coming_soon` like every Phase C route (router walk
  untouched). Response for a real code: valid; participant name; course
  title; field of study and recommended credit as the snapshot recorded
  them; completion date; sponsor name; the "Self study" program type.
  All of it **from the snapshot**, never from today's course row — the
  certificate is the frozen fact being verified.
- Unknown, malformed, or revoked-in-some-future-sense codes all answer
  the identical not-found shape. No existence oracle, no distinction.
- Frontend `/certificates/verify` (a code-entry box) and
  `/certificates/verify/{code}` (the result card, shareable URL).
  **Namespace deliberately avoids 017's `/verify`** — that path is email
  verification and stays untouched; a test pins both routes resolving
  to their own pages.
- Caddy rate limit on the verification GET mirroring the signup rule —
  it is a public unauthenticated lookup and the only cost of politeness
  is a config line.

### 4. Participant surface
- The participant's certificates page (extend what exists): download,
  the verification code with a copy affordance, and the shareable
  verification link — so a participant can hand a board the link
  instead of the PDF if they prefer.

### 5. Tests and docs
- Delivery: completion with a working console backend sends exactly one
  `certificate` email with the attachment logged; completion with a
  send that raises still completes, marks `failed`, and the admin
  resend recovers it to `sent`.
- Verification: real code returns snapshot facts (test mutates the
  course after issuance and asserts the response did not move);
  unknown/malformed identical; mode matrix; both `/verify` namespaces
  resolve independently; rate-limit config present.
- COMPLIANCE.md: 9.01 row updated — documentation is delivered
  immediately by email and on demand from the account, well inside 60
  days; 9.01.1 row for the verification page as the sponsor's
  confirmation channel. Cite from the PDF.
- OPERATIONS.md: a short "Certificate delivery (019)" note — what
  `failed` means, the resend button, and that verification is public by
  design.

## Out of scope
- Per-jurisdiction credit display (020) and waiting-list invitations
  (021).
- Any change to certificate content, the snapshot timing, or the
  completion rules.
- Revocation. No certificate has ever needed revoking; if one does, it
  is its own carefully-considered feature, not a status enum stub built
  on speculation.
- Automatic delivery retries (flag + human button only, see above).
- Email-change flows (still admin-only, per 017's known gap).

## Acceptance
1. Completing a course in dev issues the certificate, sends the email
   through the console backend with the PDF attached, and marks
   delivery `sent`; a forced send failure leaves the completion intact,
   marks `failed`, and Resend recovers it.
2. The printed verification line appears on newly rendered PDFs;
   backfilled dev certificates verify by code with unchanged PDFs.
3. The public page confirms a real certificate from snapshot data even
   after the course's title/credit change, and answers identically for
   unknown and malformed codes.
4. `/certificates/verify/*` is public at open and 404 in coming_soon;
   017's `/verify` is untouched; the 015 router walk is green with its
   allowlist unchanged.
5. Full suite green; changelog entry written; nothing in the completion
   path gained a new failure mode (the delivery tests prove it).

## Notes for Claude Code
- The send-after-commit ordering matters: a certificate email about a
  completion that then rolled back would be a lie in someone's inbox.
- The verification response is assembled from the snapshot columns/JSON
  only; if a fact isn't in the snapshot, it does not appear, even if
  the live course row has it.
- ROADMAP: mark 019 built ahead of ship. Phase C remaining after this:
  020, 021, and the open flip itself.
