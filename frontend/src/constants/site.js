// 022: the words and the origin come from site.config.json — the same
// file vite.config.js bakes into index.html's static tags and the
// identity script draws onto og.png. One place, three readers.
import site from "../../site.config.json";

export const siteName = site.name;
export const siteTitle = `${site.name} — ${site.tagline}`;
