/**
 * 027: the stepper's derivations from the reader payload — where to land,
 * what state each section is in, how the progress line counts.
 */
import { describe, expect, it } from "vitest";
import {
  gatedSectionCount,
  positionLabel,
  progressLabel,
  resumeKey,
  sectionStates,
  sectionsCompleted,
} from "./stepper.js";

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

// --- 037: where the participant is -----------------------------------------

describe("gatedSectionCount", () => {
  it("is the server's figure when the payload carries one", () => {
    expect(gatedSectionCount({ ...lesson(), section_count: 7 })).toBe(7);
  });

  it("falls back to the payload's own body sections", () => {
    expect(gatedSectionCount(lesson())).toBe(4);
  });
});

describe("positionLabel", () => {
  it("names the lesson and the section", () => {
    const l = { ...lesson(), lesson_position: 4, lesson_count: 6, section_count: 7 };
    expect(positionLabel(l, "s2")).toBe("Lesson 4 of 6 · Section 2 of 7");
  });

  it("keeps the section wording for front matter and reference", () => {
    const l = { ...lesson(), lesson_position: 4, lesson_count: 6 };
    expect(positionLabel(l, "fm")).toBe("Lesson 4 of 6 · Start here");
    expect(positionLabel(l, "gl")).toBe("Lesson 4 of 6 · Reference");
  });

  it("shows the section half alone when the lesson half is absent", () => {
    expect(positionLabel(lesson(), "s2")).toBe("Section 2 of 4");
  });
});

describe("sectionsCompleted", () => {
  it("takes the server's count", () => {
    const l = { ...lesson({ locked: ["s2", "s3", "s4"] }), sections_completed: 2 };
    expect(sectionsCompleted(l, {})).toBe(2);
  });

  it("counts a gate cleared in this session, before the refetch lands", () => {
    // The payload still says nothing is answered and nothing is complete;
    // the session holds verdicts for both questions placed after s1.
    const l = {
      ...lesson({ locked: ["s2", "s3", "s4"] }),
      sections_completed: 0,
    };
    expect(sectionsCompleted(l, {})).toBe(0);
    expect(sectionsCompleted(l, { q1: {}, q2: {} })).toBe(1);
  });

  it("never counts a locked section", () => {
    // s3 carries q3; s2 and s4 carry none, so only their lock keeps them
    // out of the count.
    const open = { ...lesson(), sections_completed: 0 };
    expect(sectionsCompleted(open, { q1: {}, q2: {}, q3: {} })).toBe(4);
    const shut = { ...lesson({ locked: ["s3", "s4"] }), sections_completed: 0 };
    expect(sectionsCompleted(shut, { q1: {}, q2: {} })).toBe(2);
  });
});
