# current-feature.md — Coming-soon cleanup and favicon swap

Feature number: next in the CHANGELOG.md sequence (assign when writing the entry).

## Goal

While `site_mode` is `coming_soon`, the only public page shows the superCPE
wordmark and "Coming Soon" and makes no claim that superCPE offers CPE, has a
course, or is on the NASBA Registry. Replace the favicon set with a new SVG.

## Why (compliance)

- **8.01** requires eleven items made available in advance for externally sold
  courses. The current page discloses a partial subset (format, subject) and
  promises the rest later. Recorded decision: partial disclosure is worse than
  none. Remove all program description.
- **8.01(11)** — the official NASBA sponsor statement applies only "if an
  approved NASBA sponsor." superCPE is not registered and `may_claim_registry`
  is false. "superCPE is registered on the National Registry of CPE Sponsors."
  is false and must not render.
- The ASC 842 course was abandoned (ASC842-PCX is a pipeline validator only).

Verify both citations against `docs/standards/*.txt` before writing them
anywhere. Do not cite from memory.

## In scope

1. ComingSoon page copy and layout.
2. Browser tab title, meta description, OG/Twitter tags, web manifest.
3. Favicon and app icons from the new SVG.
4. Report-only audit of claim language elsewhere.

## Out of scope — flag, don't build

- `site_mode` logic, routing, gating, auth. `/login` and admin routes must work
  exactly as before in `coming_soon` mode.
- Copy on Catalog, HowItWorks, Policies, email templates, certificate template —
  audit and report only.
- Using the new icon anywhere except favicon/app icons (no header, page body,
  certificate, email, or og.png use). Flaticon's license prohibits logo or
  trademark use.
- New npm or pip dependencies. Adding a frontend test runner.
- Backend changes.

## Locators

- `frontend/src/pages/ComingSoon/` (component and styles)
- `frontend/index.html`
- `frontend/site.config.json` — check whether it is the source for title/meta; if so, edit there
- `frontend/scripts/` — check for icon or og image generators
- `frontend/public/`: `logo.svg` (new, Flaticon), `favicon.ico`,
  `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `og.png`, `site.webmanifest`
- Anything setting the tab title: `grep -rn "document.title\|<title" frontend/src frontend/index.html`
- Never edit `frontend/dist/`.

## Data model

None. No migration.

## Tasks

### 1. Recon — report before editing

Print a short report, then continue:
- Source of the tab text "Self Study for CPA's" (and variants: "Self-study",
  "self study", "for licensed CPAs").
- `grep -rni "national registry" frontend/src backend/app` — for each hit: file,
  route/surface, and whether it renders only when `may_claim_registry` is true.
- `grep -rni "842\|practical expedient" frontend/src`.
- Whether ComingSoon contains a waiting-list form.
- Whether `og.png` contains text, and what it says.

### 2. ComingSoon page

Renders exactly:
- `<h1>superCPE</h1>` (exact casing)
- "Coming Soon" beneath it
- If a waiting-list form exists: keep it working, claim-free copy only — label
  "Email", button "Notify me", success "You're on the list." No description of
  what they'll be notified about.
- Any existing operator login link stays.

Remove everything else: tagline, "What this is", course description, ASC 842
text, "Full program details…" paragraph, Registry sentence. Delete now-unused
imports, styles, and copy constants rather than commenting them out.

Layout: centered horizontally and vertically in the viewport. Reuse existing CSS
variables and fonts — no new typeface or palette. Wordmark is the large element;
"Coming Soon" smaller. Works down to 320px wide. No animation. No icon on the page.

### 3. Tab and metadata (edit at the source of truth)

- Landing page `<title>superCPE</title>`. If a title helper appends a suffix
  such as " — Self-study CPE…", remove the suffix.
- `meta description`, `og:title`, `og:description`, `twitter:title`,
  `twitter:description`: title "superCPE", description "Coming Soon". Nothing
  mentioning CPE, CPAs, courses, or credit.
- `site.webmanifest`: `name` and `short_name` "superCPE"; `description`
  "Coming Soon" or removed; icon paths match task 4.

### 4. Favicon

- Rename `frontend/public/logo.svg` → `frontend/public/favicon.svg` (use `mv`;
  it may be untracked). The name reflects its only permitted use.
- `index.html` head — replace all existing icon link tags with:
  ```html
  <link rel="icon" href="/favicon.svg?v=2" type="image/svg+xml">
  <link rel="icon" href="/favicon.ico?v=2" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
  ```
- Regenerate from `favicon.svg`: `favicon.ico` (16, 32, 48),
  `apple-touch-icon.png` (180×180, opaque white background, ~12% padding —
  iOS renders transparency as black), `icon-192.png`, `icon-512.png`.
  Use an existing generator in `frontend/scripts/` if present; otherwise a tool
  already on the machine (`rsvg-convert`, ImageMagick, `sips`). If none is
  available, stop and tell me what to install.
- `og.png`: if it contains claim text and a generator exists, regenerate with
  only the "superCPE" wordmark on the existing background, no icon. Otherwise
  leave it and list it under Known gaps.

### 5. COMPLIANCE.md

Update existing rows (don't duplicate):
- 8.01 — the `coming_soon` public surface makes no program claims; the eleven
  items publish with the course before registration opens.
- 8.01(11) — Registry/sponsor statement renders only when `may_claim_registry`
  is true. Write this only if recon confirmed every hit is gated; otherwise
  record the gap.

## Tests

- Backend: full pytest suite passes unchanged.
- Frontend: if a test runner already exists, add a ComingSoon test — renders
  "superCPE" and "Coming Soon"; does not contain "National Registry", "842",
  "CPE credit", "Self-study", or "licensed CPA". If no runner exists, skip.
- `npm run build` passes.
- `grep -i "self study\|self-study" frontend/dist/index.html` returns nothing.
- `grep -c "favicon.svg" frontend/dist/index.html` returns ≥ 1.

## Acceptance

- Local (`npm run dev`, `coming_soon`): landing shows only superCPE + Coming
  Soon (+ neutral waitlist form if one existed). Tab reads "superCPE" with the
  new icon after a hard refresh.
- `/login` and admin routes reachable as before.
- Recon report delivered, including every Registry hit and its gating status.
- Operator (Dane), production, after deploy:
  - `curl -s https://supercpe.com | grep -o "<title>[^<]*</title>"` → `<title>superCPE</title>`
  - `curl -sI https://supercpe.com/favicon.svg` → 200, `image/svg+xml`
  - `curl -i https://supercpe.com/api/v1/health` → 200
  - Visual check in a private window.

## When done

1. Lint (if configured) and build pass; `git status --porcelain` shows only intended files.
2. Commit to `main`, push. Tell me to deploy using the sha from
   `git rev-parse --short origin/main`.
3. After I confirm the production checks, append the CHANGELOG.md entry in the
   existing format (What changed / Standards touched / Decisions / Known gaps).
   Decisions to record: (a) no program claims before registration, per the 8.01
   partial-disclosure decision; (b) `favicon.svg` is Flaticon-licensed,
   favicon-only, not a brand mark. Known gaps: every out-of-scope hit from recon.
