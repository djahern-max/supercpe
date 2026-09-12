/**
 * 027: what comes after a lesson, from the enrollment detail alone.
 */
import { describe, expect, it } from "vitest";
import { deriveNextStep, reviewRemaining } from "./nextStep.js";

function enrollment(overrides = {}) {
  return {
    enrollment_id: 5,
    status: "active",
    completion: null,
    open_attempt_id: null,
    assessment_available: false,
    failed_attempts: 0,
    retakes_remaining: 4,
    lessons: [
      { package_id: 11, position: 1, title: "One", kind: "text", done: true, review_answered: 2, review_total: 2 },
      { package_id: 12, position: 2, title: "Two", kind: "text", done: false, review_answered: 1, review_total: 3 },
      { package_id: 13, position: 3, title: "Three", kind: "text", done: false, review_answered: 0, review_total: 2 },
    ],
    ...overrides,
  };
}

describe("deriveNextStep", () => {
  it("names the next unread lesson, in position order, skipping this one", () => {
    expect(deriveNextStep(enrollment(), "12")).toEqual({
      kind: "lesson",
      to: "/my/courses/5/lessons/13",
      label: "Next lesson: Three",
      title: "Three",
      course: "/my/courses/5",
    });
    expect(deriveNextStep(enrollment(), "13").to).toBe("/my/courses/5/lessons/12");
  });

  it("offers the assessment only when the whole course is read and it is available", () => {
    const lessons = enrollment().lessons.map((l) => ({ ...l, done: true }));
    expect(deriveNextStep(enrollment({ lessons }), "13").kind).toBe("course");
    expect(
      deriveNextStep(enrollment({ lessons, assessment_available: true }), "13")
    ).toMatchObject({
      kind: "assessment",
      to: "/my/courses/5/assessment",
      label: "Take the qualified assessment",
    });
    expect(
      deriveNextStep(
        enrollment({ lessons, assessment_available: true, failed_attempts: 1, retakes_remaining: 3 }),
        "13"
      ).label
    ).toBe("Re-take the qualified assessment (3 left)");
  });

  it("resumes an open attempt before anything else", () => {
    expect(deriveNextStep(enrollment({ open_attempt_id: 9 }), "12")).toMatchObject({
      kind: "assessment",
      label: "Resume the assessment",
    });
  });

  it("points at the course page once completed", () => {
    expect(
      deriveNextStep(enrollment({ completion: { completion_id: 1 } }), "12")
    ).toMatchObject({ kind: "course", to: "/my/courses/5" });
  });
});

describe("reviewRemaining", () => {
  it("is this lesson's unanswered count", () => {
    expect(reviewRemaining(enrollment(), "12")).toBe(2);
    expect(reviewRemaining(enrollment(), "11")).toBe(0);
    expect(reviewRemaining(enrollment(), "99")).toBe(0);
  });
});
