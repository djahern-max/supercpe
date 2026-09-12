/**
 * 027: the reader shows one section at a time. These are the pure
 * derivations the stepper makes from the payload the server already
 * serves — nothing here decides what is open (the server did, per
 * section, by withholding `markdown`), and nothing here is written back.
 *
 * The "reading chain" is what Continue walks: front matter first, then
 * the body sections in manifest order. Glossary and appendix sections are
 * reference material, listed apart and open at any time (they are the
 * 7.02.5 exclusions, ungated for the same reason they are uncounted).
 */

export const CHAIN_ROLES = ["front_matter", "body"];
export const REFERENCE_ROLES = ["glossary", "appendix"];

export function readingChain(sections) {
  return sections.filter((s) => CHAIN_ROLES.includes(s.role));
}

export function bodySections(sections) {
  return sections.filter((s) => s.role === "body");
}

export function referenceSections(sections) {
  return sections.filter((s) => REFERENCE_ROLES.includes(s.role));
}

/** Every review question placed after `sectionKey`, in package order. */
export function questionsAfter(lesson, sectionKey) {
  return lesson.questions.filter((q) => q.after_section === sectionKey);
}

/**
 * Answered on the server (`answered` in the payload) or graded in this
 * session (`results`, the verdicts the Reader keeps for 5.01.2.2).
 */
export function isAnswered(question, results) {
  return question.answered || results[question.question_key] !== undefined;
}

export function allAnswered(lesson, results) {
  return lesson.questions.every((q) => isAnswered(q, results));
}

/**
 * Where to land when the URL names no section: the first section not yet
 * read, as far as the payload can say. The payload knows which gates have
 * been passed (every question after a section answered) and which
 * sections are locked; it does not know whether an ungated section was
 * read. So: the section after the last passed gate, if it is open;
 * otherwise that gate's own section; and front matter when no gate has
 * been passed at all.
 */
export function resumeKey(lesson, results) {
  const chain = readingChain(lesson.sections);
  if (chain.length === 0) return lesson.sections[0]?.section_key ?? null;
  let lastPassed = -1;
  chain.forEach((section, index) => {
    const placed = questionsAfter(lesson, section.section_key);
    if (placed.length > 0 && placed.every((q) => isAnswered(q, results))) {
      lastPassed = index;
    }
  });
  if (lastPassed === -1) return chain[0].section_key;
  const next = chain[lastPassed + 1];
  if (!next || next.locked) return chain[lastPassed].section_key;
  return next.section_key;
}

/**
 * The state of every section for the table of contents: `read`,
 * `current`, `unread` (open, not read), or `locked`. "Read" is derived —
 * everything before the resume point — plus whatever this session has
 * moved on from (`visited`, browser state, never a record).
 */
export function sectionStates(lesson, results, currentKey, visited) {
  const chain = readingChain(lesson.sections);
  const resume = resumeKey(lesson, results);
  const resumeIndex = chain.findIndex((s) => s.section_key === resume);
  const derivedRead = new Set(
    chain.slice(0, Math.max(resumeIndex, 0)).map((s) => s.section_key)
  );
  const states = {};
  for (const section of lesson.sections) {
    const key = section.section_key;
    if (section.locked) states[key] = "locked";
    else if (key === currentKey) states[key] = "current";
    else if (derivedRead.has(key) || visited.has(key)) states[key] = "read";
    else states[key] = "unread";
  }
  return states;
}

/**
 * The progress line: "Section 4 of 14" counts body sections only. Front
 * matter is the start, reference sections say "Reference".
 */
export function progressLabel(lesson, sectionKey) {
  const bodies = bodySections(lesson.sections);
  const index = bodies.findIndex((s) => s.section_key === sectionKey);
  if (index >= 0) return `Section ${index + 1} of ${bodies.length}`;
  const section = lesson.sections.find((s) => s.section_key === sectionKey);
  if (section?.role === "front_matter") return "Start here";
  return "Reference";
}
