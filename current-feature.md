# current-feature.md

## Goal

Make the create-course form on `/admin/courses` usable on a phone-width
viewport. Today the course code field, title field, and **Create course**
button sit in a fixed three-across row; at ~390–500px the button is clipped by
the card edge and is partly or fully unreachable.

Desktop appearance must not change.

## In scope

- The create-course form row on the admin Courses page.
- If that row's styling comes from a shared admin form-row class used by other
  admin pages (Packages, Experts, Sponsor, Jurisdictions), fix it once at the
  shared class rather than adding a page-specific override.

## Out of scope

- The admin header/nav. It already collapses to a **Menu** button at narrow
  widths; leave it alone.
- Any visual restyle — no palette, type, spacing, or component redesign beyond
  what wrapping requires.
- Course list/table layouts on this page (empty today; separate feature if they
  need work).
- Any backend, route, schema, or course-creation behavior change.
- Adding a CSS framework, component library, or any new dependency.

## Locators

Not pinned in this spec — find them and record the actual paths in the
changelog entry.

1. The admin Courses page component under `frontend/src/` (the one rendering
   the `Course code (e.g. ASC842-PCX)` and `Title` inputs and the
   `Create course` button).
2. The stylesheet rule that lays out that card/row.
3. **The existing media query that drives the admin header's Menu collapse.**
   Read its breakpoint value and reuse that exact value. Do not introduce a
   second breakpoint near it.

## Data model

No change. No migration.

## Tasks

1. Read the header-collapse media query; note the breakpoint value for use
   below and for the changelog entry.
2. Convert the form row to a wrapping flex row: `display: flex`,
   `flex-wrap: wrap`, and a `gap` matching the existing spacing between the
   controls.
3. Replace any fixed widths on the two inputs with a flex basis, e.g.
   `flex: 1 1 14rem`, plus `min-width: 0` on each so a flex item cannot force
   the row wider than the card. Confirm `box-sizing: border-box` applies to the
   inputs and the card — inputs at `width: 100%` inside a padded card overflow
   without it.
4. At and below the header breakpoint, stack: the row becomes
   `flex-direction: column`, and each of the two inputs and the button takes
   `width: 100%`. A half-width button under a full-width input reads as a
   layout bug, so the button goes full-width too.
5. Give the button a `min-height` of at least 44px at the stacked size so it is
   a usable tap target.
6. Verify keyboard focus rings on both inputs and the button are still visible
   in the stacked layout (nothing clipped by the card's overflow).

## Tests

There is no frontend test runner in this repo, so verification is manual in a
browser at these widths:

- **390px** — controls stacked, all three fully inside the card, nothing
  clipped, no horizontal scrollbar on the page.
- **500px** — matches the second screenshot's width; same as above.
- **768px** — either wrapped or three-across, but no clipping either way.
- **1280px** — pixel-unchanged from current desktop layout.

Tab through the form at 390px and confirm focus is visible on each control.

Run existing backend tests to confirm nothing was touched there.

## COMPLIANCE.md rows

None. This is presentation only on an admin-internal page. No Section 9
certificate content, no 4.02 reviewer artifact, no participant-facing record is
affected.

## Acceptance

- At 390px, the course code field, title field, and Create course button are
  all fully visible and operable inside the card.
- No horizontal page scroll at 390px on `/admin/courses`.
- At 1280px the layout is visually identical to before the change.
- One breakpoint value governs both the header collapse and the form stack.
- No new dependencies; no backend, route, or behavior changes.

## When done

Append the next sequential CHANGELOG entry:

- **What changed** — the files touched (actual paths), the breakpoint value
  reused, and whether the fix landed on a shared admin form-row class or was
  scoped to this page.
- **Standards touched** — none.
- **Decisions** — record the shared-class vs page-scoped choice and why.
- **Known gaps** — list the production browser walkthrough at phone width as
  operator-only, not yet run by the operator. Note any other admin pages
  observed to have the same fixed-row problem but left unfixed by this spec.
