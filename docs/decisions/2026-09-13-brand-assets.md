# Decision — Brand assets: one source directory, copied by script, and the brand mark is the sponsor mark

Recorded: 2026-09-13 (feature 033)
Status: decided
Reverses: the 022 decision that the identity assets are generated from a
placeholder (the "sC" monogram, then 024's Flaticon favicon) because no
brand existed, and the 032 Decision "The monogram is drawn as code, not
taken from the favicon". Both were stopgaps for the absence of a brand;
the brand now exists. Does not reverse any compliance decision: what any
surface *says* is unchanged.

## The decisions

1. **One source directory.** `brand/` at the repo root holds the files
   Dane produced for superCPE, LLC — owned outright, no third-party
   license — and `brand/README.md` maps each file to a role and records
   the sampled palette. Nothing in the app reads `brand/`.

2. **Copy by script, never by hand.** `frontend/scripts/sync_brand.py`
   derives every fixed-name asset the frontend and the backend need
   (favicons, manifest icons, `logo.png`, `og.png`, the manifest, the
   hashed-pipeline copies, the certificate's logo and seal, and the
   palette module). Every output is a pure function of the inputs, so a
   second run is byte-identical and `--check` refuses a stale copy; it
   runs in the test suite and on the pre-changelog lint line. The
   backend gets its own copies because it never imports from `frontend/`
   and the api image copies `backend/` only.

3. **The sponsor mark is the brand mark.** The sponsor is superCPE, LLC,
   so the certificate's default mark is the brand logo and there is no
   per-sponsor asset. `sponsor_profile.logo_path` (032) stays as an
   override — uploading a different mark still works and clearing it
   returns to the brand logo — but it is not a multi-sponsor feature; a
   real per-sponsor slot returns only if a second sponsor ever exists
   (001).

4. **HTML → PDF stays the certificate renderer.** 032's WeasyPrint
   template is kept; 033 changed the mark, the seal, the colours, and
   pinned the PDF's creation date to the snapshot's completion instant so
   renders are byte-identical and the stored-once record (9.02) can be
   checked by comparison. Fonts and images are embedded; the fetcher
   admits only files under `backend/app/assets/`.

5. **No Registry mark until approved.** The NASBA Registry logo is not
   licensed to superCPE (`may_claim_registry` is false). It belongs to no
   asset, template, card, or page, and tests assert the words "National
   Registry" appear on none of them while the claim is false.

6. **Raster sources, PNG favicons.** Dane supplied PNG and ICO only, so
   there is no SVG favicon and no vector certificate mark; every derived
   raster is a downscale from a source at more than 2× its rendered size.
   If SVGs arrive, the script is where they are wired in.

7. **The accent text colour is a tint, the true blue is for marks.** The
   brand blue (`#006afc`) is 4.70:1 on white but 4.42:1 on the page
   ground, under WCAG AA for body text; `--color-accent` is `#0066f4`
   (4.99:1 and 4.65:1), used for links and accent text, while marks,
   rules, and filled buttons use the brand tokens. The teal (`#01b6af`,
   2.53:1) is never text.

## Why

The certificate is the one artifact a participant keeps and hands to a
state board; the landing page is the only public surface until opening
day; the admin nav is used from a phone. A placeholder mark on any of
them was a stopgap. Putting the assets in one committed place and
deriving every copy from it means a rebrand is one edit, one script run,
one commit, and a stale copy cannot ship unnoticed.

What the Standards require (2026 Statement, read for 033):

- 9.01 (printed page 21) — the eleven certificate items. Nothing about
  them changed; the mark is decoration and the tests that pin each item
  as extractable text pass unchanged.
- 9.01.1 (printed pages 21–22) — the awarding entity. Still the
  "Authorized by" line from `sponsor_legal_name` in the snapshot.
- 8.01 (printed page 20) — descriptive materials. The landing page and
  the link-preview card still disclose no item; partial disclosure is
  worse than none (024).
- 9.02 / 9.02.2 (printed page 22) — retained documentation. Stored PDFs
  are never re-rendered; from 033 on they are self-contained and
  byte-comparable to their snapshot.
