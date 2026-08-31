import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 022: site identity lives in one place — site.config.json for the words,
// global.css for the colors. index.html carries %SITE_*% tokens so the
// title, description, and OG tags cannot drift from what the OG-image
// script and the page-title helper read.
const site = JSON.parse(readFileSync(new URL('./site.config.json', import.meta.url)))
const accentColor = readFileSync(
  new URL('./src/styles/global.css', import.meta.url),
  'utf8',
).match(/--color-accent:\s*(#[0-9a-fA-F]+)/)[1]

const siteMeta = () => ({
  name: 'site-meta',
  transformIndexHtml: {
    order: 'pre',
    handler(html) {
      return html
        .replaceAll('%SITE_ORIGIN%', site.origin)
        .replaceAll('%SITE_NAME%', site.name)
        .replaceAll('%SITE_TITLE%', `${site.name} — ${site.tagline}`)
        .replaceAll('%SITE_DESCRIPTION%', site.description)
        .replaceAll('%SITE_THEME_COLOR%', accentColor)
    },
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), siteMeta()],
})
