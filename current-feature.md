# Current Feature

## Feature 022, Site identity and link previews

## Goal
supercpe.com looks like itself everywhere a link to it lands: a real
favicon in the tab, a branded card when the URL is texted or posted, an
honest title and description for search engines, and the robots/sitemap
plumbing that lets indexing start now, while coming-soon, so the domain
has some standing by opening day. All metadata obeys the standing content
rules: no course facts (the 015/021 restraint — link, don't restate) and
no Registry words while `may_claim_registry` is false.

## The constraint that shapes everything
The frontend is a Vite SPA: one `index.html`, and social scrapers
(iMessage, Slack, LinkedIn, X) do not execute JavaScript. So Open Graph
tags are **static and site-wide** in `frontend/index.html`. This is fine —
the site-wide description must be course-fact-free anyway. Per-page
titles are client-side only (`document.title`, helps humans and Google,
invisible to scrapers). Per-course OG cards would need SSR or edge
injection: **out of scope**, ROADMAP note.

## In scope

### 1. Identity assets (replace every Vite default)
- A simple superCPE mark, generated as code, not sourced from anywhere:
  a wordmark/monogram SVG (suggest: "sC" or "superCPE" in the app's
  existing font/colors — read the frontend's CSS variables and reuse
  them; invent nothing off-palette).
- From it: `favicon.svg`, `favicon.ico` (32px fallback),
  `apple-touch-icon.png` (180px), and a `site.webmanifest` with name,
  theme color, and the 192/512 PNG icons.
- OG image `og.png`, 1200×630: the wordmark, the one-line tagline (see
  below), the domain. Generate it programmatically (Pillow or
  node-canvas — whatever the repo can run) and **commit the generator
  script** beside the asset so Dane can regenerate after any rebrand.
- All referenced with hashed or versioned filenames (Vite's asset
  pipeline where possible) so stale favicon caches don't survive a
  rebrand; the manifest and apple-touch icon live in `public/` with
  explicit names as those must.

### 2. Metadata in index.html
- `<title>`: "superCPE — Self-Study CPE for CPAs" (or Dane's tagline;
  pick one line and use it everywhere).
- `<meta name="description">`, `og:title`, `og:description`,
  `og:image` (absolute https URL — scrapers resolve nothing),
  `og:url`, `og:type=website`, `og:site_name`,
  `twitter:card=summary_large_image`, canonical link, theme-color.
- Content rules, enforced by test where cheap: a backend test reads
  `frontend/index.html` and asserts "National Registry" absent and none
  of: a credit figure, "QAS", a price. The description describes the
  sponsor, not the course — e.g. "Self-study continuing professional
  education for CPAs, built to the NASBA Standards." (Claiming to
  *follow* the Standards is a statement about design, not a Registry
  claim — but keep even that modest; Dane has final word on the line.)
- Client-side `document.title` per route (catalog, course, register,
  verify, policies, admin unchanged) — small helper, no dependency.

### 3. robots.txt and sitemap
- `robots.txt` (static, `public/`): allow all, `Disallow: /admin`,
  and the `Sitemap:` line. The coming-soon page is *meant* to be
  indexed — that is the point of shipping this before open.
- `GET /sitemap.xml` served by the **backend**, mode-aware:
  - `coming_soon`: the root URL only.
  - `open`: root, `/courses`, each published course page, the policies
    page, `/certificates/verify`, `/register`.
  This is a new **intentionally public** route: add it to
  `INTENTIONALLY_PUBLIC` marked `022` — the designed mechanism for
  exactly this, and the router walk will hold everyone to it.
  Caddy needs a rewrite/handle so `/sitemap.xml` reaches the API
  rather than the static frontend — follow the existing Caddyfile's
  structure and say in the changelog how it was routed.
- No analytics, no third-party scripts, no tracking pixels — 015's
  decision stands; this feature is metadata only. If Dane ever wants
  analytics it is its own privacy-considered decision.

### 4. Small honesty details
- JSON-LD `Organization` block (name, url, logo) in index.html —
  minimal, nothing it can't back.
- `og:image` and canonical use the production origin from one obvious
  constant in the frontend config, not scattered literals.
- The 404/unmatched path already renders the gate/catalog correctly;
  verify `document.title` doesn't lie on it.

### 5. Tests and docs
- The index.html content-rule test above; sitemap mode matrix
  (coming_soon vs open, published-only courses listed); router walk
  green with the one new allowlisted entry carrying its feature
  number; robots.txt served with the sitemap line.
- OPERATIONS.md: "Site identity (022)" — how to regenerate the OG
  image and favicons after a rebrand (run the committed script), and a
  note that link-preview caches (iMessage, Slack) are sticky: after
  deploy, previews refresh on their own schedule, and the only lever
  is time or a query-string variant when testing.
- ROADMAP: per-course OG cards (needs SSR/edge injection) recorded as
  an improvement note; 022 added to the plan as the first
  post-021 reality-demanded feature.

## Out of scope
- Per-course/per-page OG tags (SSR — ROADMAP).
- Analytics of any kind.
- Paid or off-site SEO, ads, social accounts — not code.
- A real designed brand. The generated mark is deliberately plain and
  regenerable; a designer can replace the assets later by rerunning or
  replacing the script, and nothing else moves.
- Blog/content marketing infrastructure — if Dane ever wants it, its
  own feature.

## Acceptance
1. Local build: browser tab shows the superCPE favicon; no Vite asset
   remains in `public/` or `index.html`.
2. `curl https://localhost.../index.html` (or the built file) contains
   the full OG/twitter set with absolute image URL; the content-rule
   test passes.
3. Texting/pasting the production URL after deploy renders a card with
   the image and title (operator's by-eye step; caches may lag —
   OPERATIONS.md says so).
4. `/sitemap.xml` lists only the root in `coming_soon` and the full
   public set at open (test env); `/robots.txt` allows all, disallows
   `/admin`, names the sitemap; the router walk is green with exactly
   one new allowlisted route marked 022.
5. Route changes update the tab title; admin pages unchanged.
6. Full suite green; changelog entry written.

## Notes for Claude Code
- Read the frontend's existing colors/typography before drawing
  anything; the mark should look like the site, not like a default.
- Absolute URLs in OG tags: scrapers do not resolve relative paths.
- Keep the tagline in one place (a constant) — index.html, the OG
  image script, and the JSON-LD all read it.
