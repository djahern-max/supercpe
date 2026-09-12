/**
 * 027: the stepper's derivations from the reader payload — where to land,
 * what state each section is in, how the progress line counts.
 */
import { describe, expect, it } from "vitest";
import { progressLabel, resumeKey, sectionStates } from "./stepper.js";

function section(key, role, locked = false) {
  return { section_key: key, role, title: key, locked, markdown: locked ? null : "…" };
}

function lesson({ answered = [], locked = [] } = {}) {
  return {
    lesson_id: "L1",
    sections: [
      section("fm", "front_matter"),
      section("s1", "body"),
      section("s2", "body", locked.includes("s2")),
      section("s3", "body", locked.includes("s3")),
      section("s4", "body", locked.includes("s4")),
      section("gl", "glossary"),
      section("ap", "appendix"),
    ],
    media: [],
    questions: [
      { question_key: "q1", after_section: "s1", answered: answered.includes("q1") },
      { question_key: "q2", after_section: "s1", answered: answered.includes("q2") },
      { question_key: "q3", after_section: "s3", answered: answered.includes("q3") },
    ],
  };
}

describe("resumeKey", () => {
  it("is front matter when no gate has been passed", () => {
    expect(resumeKey(lesson({ locked: ["s2", "s3", "s4"] }), {})).toBe("fm");
  });

  it("needs every question after a section, not the last one answered", () => {
    expect(resumeKey(lesson({ answered: ["q2"], locked: ["s2", "s3", "s4"] }), {})).toBe("fm");
  });

  it("is the section after the last passed gate", () => {
    expect(resumeKey(lesson({ answered: ["q1", "q2"], locked: ["s4"] }), {})).toBe("s2");
    expect(resumeKey(lesson({ answered: ["q1", "q2", "q3"] }), {})).toBe("s4");
  });

  it("counts a verdict graded this session as answered", () => {
    const results = { q1: { correct: true }, q2: { correct: false } };
    expect(resumeKey(lesson({ locked: ["s4"] }), results)).toBe("s2");
  });

  it("stays on the gate section while the next is still locked", () => {
    // The refetch has not landed yet: the payload still locks s2.
    const results = { q1: {}, q2: {} };
    expect(resumeKey(lesson({ locked: ["s2", "s3", "s4"] }), results)).toBe("s1");
  });
});

describe("sectionStates", () => {
  it("marks read, current, unread, and locked", () => {
    const states = sectionStates(
      lesson({ answered: ["q1", "q2"], locked: ["s4"] }),
      {},
      "s3",
      new Set()
    );
    expect(states).toEqual({
      fm: "read",
      s1: "read",
      s2: "unread",
      s3: "current",
      s4: "locked",
      gl: "unread",
      ap: "unread",
    });
  });

  it("adds what this session has moved on from", () => {
    const states = sectionStates(
      lesson({ answered: ["q1", "q2"], locked: ["s4"] }),
      {},
      "s3",
      new Set(["s2", "gl"])
    );
    expect(states.s2).toBe("read");
    expect(states.gl).toBe("read");
  });
});

describe("progressLabel", () => {
  it("counts body sections only", () => {
    const l = lesson();
    expect(progressLabel(l, "s1")).toBe("Section 1 of 4");
    expect(progressLabel(l, "s4")).toBe("Section 4 of 4");
    expect(progressLabel(l, "fm")).toBe("Start here");
    expect(progressLabel(l, "gl")).toBe("Reference");
    expect(progressLabel(l, "ap")).toBe("Reference");
  });
});
