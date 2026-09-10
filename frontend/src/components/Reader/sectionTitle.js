/**
 * 023c F3: a section's markdown usually opens with a heading that repeats
 * the manifest section title, and the reader already prints that title
 * above the section. When the two match, the heading is dropped from the
 * rendered markdown so the title appears once.
 *
 * Reader-side only. The package is not changed and the word count is not
 * touched: `count_words` runs on the shipped markdown in the backend, and
 * the manifest title was never part of the count, so the heading's words
 * are counted exactly once before and after this.
 */

const HEADING = /^(#{1,3})\s+(.+?)\s*#*\s*$/;

function normalize(text) {
  return (text || "")
    .replace(/[*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function stripLeadingTitle(markdown, title) {
  if (!markdown) return markdown;
  const lines = markdown.split("\n");
  let first = 0;
  while (first < lines.length && lines[first].trim() === "") first += 1;
  const heading = first < lines.length ? lines[first].match(HEADING) : null;
  if (!heading || normalize(heading[2]) !== normalize(title)) return markdown;
  return lines.slice(first + 1).join("\n");
}
