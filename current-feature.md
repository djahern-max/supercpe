# current-feature.md — Site header

Feature number: next in the CHANGELOG.md sequence (assign when writing the entry;
024 was the coming-soon cleanup).

## Goal

One header component, rendered on every surface that is not the coming-soon page
and not `/admin/*`. It carries the wordmark, the two or three links that belong
to the viewer's role, the signed-in email, and a Sign out button. Today a
participant who signs in has no way to sign out, no way back to the catalog, and
no link to `/account` — the only way out is deleting the session cookie by hand.

This is chrome. It adds no course fact, no claim, and no new gating.

## Why (compliance)

Mostly this is a usability hole, not a compliance one. Two paragraphs do bear on
it, and both are constraints on the header rather than reasons for it:

- **8.01 / 8.01(11)** — 024 recorded the decision that partial disclosure is
  worse than none, and that the Registry sentence must not render while
  `may_claim_registry` is false. A header that renders above the coming-soon page
  would put "Courses" and a price-bearing catalog link on a page that 024
  deliberately stripped to a wordmark. **The header must not render there.** See
  task 3.
- **4.05.3(1) and (4)** — 011's COMPLIANCE row names `/how-it-works` as the
  surface answering the overview-of-topics and navigation-instructions items. A
  page that satisfies a Standard but is linked from nothing is weaker than one
  that is reachable. Recon task 1 checks whether anything currently links to it.
  If nothing does, the header link is a small real improvement; say so in the
  changelog rather than claiming the header satisfies 4.05.3 itself, which it
  does not.

Verify both citations against `docs/standards/*.txt` before writing them into
COMPLIANCE.md or the changelog. Do not cite from memory.

Note on 015's "not linked from any page" rule for `/login`: that rule was about
the coming-soon landing page, which must not advertise what is behind it. It is
not a rule against a Sign in link on the open site. The header does not render in
coming_soon, so the rule is untouched. State this in the changelog so it does not
read as a reversal.

## In scope

1. A `SiteHeader` component and its styles.
2. A small site-mode context so `SiteGate` and `SiteHeader` share one
   `GET /api/v1/site` read instead of two.
3. Rendering the header in `App.jsx`, with two null cases.
4. Report-only audit of what currently links where.

## Out of scope — flag, don't build

- A footer. Separate decision.
- A hamburger or any JS-driven menu. The header wraps; that is the mobile story.
- Any change to `SiteGate`'s gating decision, `RequireRole`, `roleHome`, or which
  paths are gated. The header reads session and site mode; it decides nothing.
- `AdminNav`. It keeps its links, its email, and its Sign out; the header returns
  null under `/admin/*` precisely so nothing there has to change.
- Stripe, checkout, prices, the coming-soon page's contents.
- New npm dependencies, an icon in the header (Flaticon's license — 024), a
  frontend test runner.
- Backend changes. No route, no schema, no migration.

## Locators

- `frontend/src/App.jsx` — routing and the role wrappers
- `frontend/src/auth/SessionContext.jsx` — `useSession()` already exposes
  `account` (id, email, role, must_change_password), `loading`, and `signOut`
- `frontend/src/auth/RequireRole.jsx` — `roleHome(role)` already maps role → home
  path; reuse it, do not restate the mapping
- `frontend/src/components/SiteGate/SiteGate.jsx` — the existing
  `GET /api/v1/site` read and the exact coming-soon condition
- `frontend/src/api/site.js` — `getSite()`
- `frontend/src/admin/AdminNav.jsx` and `.module.css` — the pattern to follow for
  a nav row, and the file that must not change
- `frontend/src/styles/global.css` — the CSS variables to reuse
- Never edit `frontend/dist/`.

## Data model

None. No migration.

## Tasks

### 1. Recon — report before editing

Print a short report, then continue:

- `grep -rn "how-it-works" frontend/src` — does anything link to it today?
- `grep -rn "/policies" frontend/src` — 011 said the course page links the
  policies; confirm, and note anything else that links there.
- `grep -rn "/register" frontend/src/pages/Login` — does the login page offer a
  create-account link, and does `Login.jsx` redirect an already-signed-in
  account, or render the form anyway?
- Every page component that renders `AdminNav`, and whether any non-admin page
  renders it.
- Whether any page already renders its own top-of-page wordmark or back link that
  the header would duplicate (check `MyCourses`, `MyCourse`, `Account`,
  `CoursePage`, `Catalog` — screenshot shows `CoursePage` has a bare "Courses"
  breadcrumb above the title).
- Whether `usePageTitle` or anything else assumes it is the only thing above
  `<main>`.

If the recon shows `CoursePage` and friends have their own breadcrumb, keep it.
A breadcrumb and a header are different things and both can stay; just report it.

### 2. Site-mode context

New `frontend/src/site/SiteContext.jsx` (or alongside `auth/` — match whatever
convention the recon finds):

- `SiteProvider` calls `getSite()` once on boot and exposes
  `{ site, loading, failed }` with the same failure posture `SiteGate` has today:
  a failed read is not fatal.
- `useSite()`.
- `SiteGate` is rewritten to consume it. Its decision must not change:
  fall through on failure, render nothing while loading, render children when
  `site_mode === "open"` or an account is present, otherwise `ComingSoon`. Keep
  the existing comment block; it is still accurate.
- `SiteProvider` wraps `<Routes>` inside `SessionProvider` in `App.jsx`.

If this turns out to be more churn than it is worth, the fallback is for
`SiteHeader` to call `getSite()` itself and accept the duplicate request. Take the
fallback only if the provider breaks a test, and say which you took in the
changelog.

### 3. SiteHeader — when it renders

Returns `null` in exactly these cases:

1. `loading` from either context is true, or the site read has not answered.
2. The coming-soon condition: `site.site_mode !== "open"` and no `account`. This
   is the same condition `SiteGate` uses to render `ComingSoon` — derive it from
   one shared helper so the two can never drift. That drift is the compliance
   risk (8.01, above), so it gets a helper and a comment, not a copied
   expression.
3. `useLocation().pathname` starts with `/admin` — `AdminNav` owns that chrome.
4. On `/change-password` — an account being forced through a password change
   should not be offered navigation out of it. `RequireRole` already redirects
   them back; a header there would just produce a link that bounces.

It renders everywhere else, including `/login`, the reader, the player, and the
assessment. There is no Standards requirement for a distraction-free assessment
surface; attempts are scored server-side and the header changes nothing about
that. Do not invent one.

### 4. SiteHeader — what it renders

Left: `superCPE` wordmark, linking to `roleHome(account.role)` when signed in and
`/` when not. Text only, no icon (024 — Flaticon's license permits favicon and
app-icon use only).

Right, by role:

- **No account** — `Courses` (`/courses`), `How it works` (`/how-it-works`),
  `Sign in` (`/login`), `Create account` (`/register`).
- **participant** — `My courses` (`/my/courses`), `Courses` (`/courses`),
  `Account` (`/account`), then the email, then `Sign out`.
- **reviewer** — `Review` (`/review`), then the email, then `Sign out`.
- **admin** — unreachable (task 3 case 3), but handle it as reviewer rather than
  crashing if someone changes the null rule later.

`Sign out` calls `signOut()` from `useSession()` and then navigates to `/`. Not
`/login`: a participant signing out should land on the public face of the site,
and in coming_soon `SiteGate` will show them the coming-soon page, which is
correct. `AdminNav` keeps its own `navigate("/login")`.

Rules the header must hold to:

- No course fact of any kind — no title, code, credit, price, field of study.
  016's rule that the frontend adds no course fact of its own applies here too.
- The strings "National Registry", any sponsor ID, and the NASBA sponsor
  statement appear nowhere in this component, conditionally or otherwise.
- No `may_claim_registry` read. The header has no business with it.
- `sponsor_name` from `/api/v1/site` is available but not used — the wordmark is
  the brand, and the sponsor name is a compliance fact that belongs on the
  certificate and the disclosure page, not in chrome.

### 5. Styling

CSS Modules, matching `AdminNav.module.css`. Existing variables and fonts only —
no new typeface, palette, or spacing scale. A single row, `flex`, wordmark left
and links right, bottom border. Wraps rather than overflowing; readable and
usable down to 320px. No animation, no sticky positioning, no shadow.

### 6. Docs

- CHANGELOG entry in the house format, including the 015-`/login` note from the
  Why section and which fallback task 2 took.
- COMPLIANCE.md: only if recon task 1 shows `/how-it-works` was unlinked. Then
  append to 011's 4.05.3 row that the page is now reachable from every signed-in
  surface. Do not open a new row and do not claim more than that.

## Acceptance

1. Signed out, `site_mode = open`: the header shows four links; Sign in reaches
   the login page; the wordmark goes to `/`.
2. Signed out, `site_mode = coming_soon`: no header markup anywhere in the
   document on `/`, `/courses`, `/courses/ATO`, or an unmatched path. Assert on
   the absence, not on it looking empty.
3. Signed in as a participant in `coming_soon`: the header renders (this is the
   case that is broken today), `Sign out` ends the session, `GET /me` then fails,
   and the browser lands on the coming-soon page.
4. Signed in as admin: `/admin/courses` looks exactly as it does today — one nav
   row, one Sign out. Diff the page to be sure.
5. Signed in as reviewer: header on `/review` and `/review/courses/:code`, with
   Sign out.
6. An account with `must_change_password`: no header on `/change-password`.
7. `/courses/ATO` at 320px: header wraps, nothing overflows horizontally.
8. Backend suite green and unchanged in count — this feature touches no backend
   file. If the count moved, something is wrong; stop and report.

## Known gaps to record

- Deleting the session cookie in the browser signs the browser out but leaves the
  `sessions` row valid until idle or absolute expiry. `Sign out` posts to
  `/auth/logout`, which revokes it properly; nothing else does. Worth a line in
  OPERATIONS.md if testers have been clearing cookies.
- No footer. `/policies` is linked from the course page (confirm in recon) and now
  from nowhere else; 8.01.1's "available" is satisfied by the course-page link,
  which is where a purchaser sees it, but a footer would be better.
- No "signed in as" affordance on `/login` if a session already exists; a tester
  with a live participant session who opens `/login` may be confused.
