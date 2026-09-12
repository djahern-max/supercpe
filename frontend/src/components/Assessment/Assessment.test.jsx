/**
 * 023c F1: the advice under a failed attempt follows the course's kind —
 * a study-guide course says re-read, a video course says re-watch. Nothing
 * per question appears either way (6.01.2 sub-ii).
 *
 * 027: the failed result says what the sitting count means — N re-takes
 * left with a Re-take button and a way back to the guide, or all N used
 * with the policy link and the sponsor's contact address — and still
 * nothing per question.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Assessment from "./Assessment.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../api/sponsor", () => ({
  getPublicSponsor: () =>
    Promise.resolve({
      name: "Sponsor",
      website: "",
      contact_email: "help@example.com",
    }),
}));

function infoFor(lessonsKind, policy = FINITE) {
  return {
    course_code: "ATO",
    title: "Account Takeover",
    question_count: 1,
    passing_pct: "70",
    ...policy,
    open_attempt_id: null,
    lessons_kind: lessonsKind,
    questions: [
      {
        question_id: 11,
        stem: "What is the first control?",
        choices: [
          { choice_id: 1, text: "MFA" },
          { choice_id: 2, text: "Nothing" },
        ],
      },
    ],
  };
}

// 028: the shipped policy is unlimited; the finite shape is what 027
// wrote and what a future integer RETAKES_ALLOWED would send again.
const FINITE = { retakes_allowed: 2, retakes_unlimited: false };
const UNLIMITED = { retakes_allowed: null, retakes_unlimited: true };

const FAILED = {
  status: "failed",
  score_pct: "0",
  passing_pct: "70",
  correct_count: 0,
  question_count: 1,
  ...FINITE,
  retakes_remaining: 1,
};

const FAILED_UNLIMITED = { ...FAILED, ...UNLIMITED, retakes_remaining: null };

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  window.confirm = () => true;
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

function button(text) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent.startsWith(text)
  );
}

async function failAnAttempt(
  lessonsKind,
  result = FAILED,
  props = {},
  policy = FINITE
) {
  const api = {
    getAssessment: () => Promise.resolve(infoFor(lessonsKind, policy)),
    start: () => Promise.resolve({ attempt_id: 7, status: "open" }),
    saveAnswers: () => Promise.resolve({}),
    submit: () => Promise.resolve(result),
    getAttempt: () => Promise.resolve({ answers: {} }),
  };
  act(() => {
    root.render(
      <MemoryRouter>
        <Assessment api={api} {...props} />
      </MemoryRouter>
    );
  });
  await flush();
  act(() => {
    button("Begin").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await flush();
  const radio = container.querySelector("input[type=radio]");
  act(() => {
    radio.click();
  });
  await flush();
  act(() => {
    button("Submit").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await flush();
  expect(container.textContent).toContain("Not passed");
  return container.textContent;
}

/** 6.01.2 sub-ii: a failed result carries nothing per question — no
 * stem, no choice, no "— correct" or "— your answer" row. The count of
 * correct answers is the outer limit of what a score already reveals. */
function expectNothingPerQuestion(text) {
  expect(text).not.toContain("What is the first control?");
  expect(text).not.toContain("MFA");
  expect(text).not.toContain("— correct");
  expect(text).not.toContain("your answer");
  expect(container.innerHTML).not.toContain("is_correct");
}

describe("Failed-attempt advice (023c F1)", () => {
  it("says re-read the guide on a study-guide course", async () => {
    const text = await failAnAttempt("text");
    expect(text).toContain("Consider re-reading the guide before trying again.");
    expect(text).not.toContain("re-watching");
  });

  it("still says re-watch on a video course", async () => {
    const text = await failAnAttempt("video");
    expect(text).toContain("Consider re-watching the lessons before trying again.");
    expect(text).not.toContain("re-reading");
  });
});

describe("Failed result under the unlimited policy (028)", () => {
  it("shows the score, the threshold, and Re-take — no count, no notice", async () => {
    const text = await failAnAttempt(
      "text",
      FAILED_UNLIMITED,
      { coursePath: "/my/courses/3" },
      UNLIMITED
    );
    expect(text).toContain("0%");
    expect(text).toContain("70 percent is required.");
    expect(button("Re-take the assessment")).toBeDefined();
    expect(button("Try again")).toBeUndefined();
    expect(container.querySelector('a[href="/my/courses/3"]').textContent).toBe(
      "Back to the study guide"
    );
    expect(text).not.toContain("re-take left");
    expect(text).not.toContain("re-takes left");
    expect(text).not.toContain("used all");
    expect(text).not.toContain("null");
    expect(container.querySelector('a[href="/policies#retakes"]')).toBeNull();
    expectNothingPerQuestion(text);
  });

  it("the intro says the assessment may be re-taken as many times as needed", async () => {
    const api = {
      getAssessment: () => Promise.resolve(infoFor("text", UNLIMITED)),
      start: () => Promise.resolve({ attempt_id: 7, status: "open" }),
      saveAnswers: () => Promise.resolve({}),
      submit: () => Promise.resolve(FAILED_UNLIMITED),
      getAttempt: () => Promise.resolve({ answers: {} }),
    };
    act(() => {
      root.render(
        <MemoryRouter>
          <Assessment api={api} />
        </MemoryRouter>
      );
    });
    await flush();
    expect(container.textContent).toContain(
      "may be re-taken as many times as needed"
    );
    expect(container.textContent).not.toContain("up to");
  });
});

describe("Failed result wording under a finite policy (027, kept by 028)", () => {
  it("with sittings left: the count, a Re-take button, and the way back", async () => {
    const text = await failAnAttempt("text", FAILED, { coursePath: "/my/courses/3" });
    expect(text).toContain("70 percent is required.");
    expect(text).toContain("You have 1 re-take left on this enrollment.");
    expect(button("Re-take the assessment")).toBeDefined();
    const back = container.querySelector('a[href="/my/courses/3"]');
    expect(back.textContent).toBe("Back to the study guide");
    expect(text).not.toContain("used all");
    expectNothingPerQuestion(text);
  });

  it("with none left (a finite mock at 0): the exhausted notice still renders", async () => {
    const text = await failAnAttempt(
      "text",
      { ...FAILED, retakes_remaining: 0 },
      { coursePath: "/my/courses/3" }
    );
    await flush();
    const body = container.textContent;
    expect(body).toContain("You have used all 2 re-takes on this enrollment.");
    expect(container.querySelector('a[href="/policies#retakes"]').textContent).toBe(
      "Read the re-take policy"
    );
    expect(body).toContain("Contact us about re-enrolling: help@example.com");
    expect(container.querySelector('a[href="mailto:help@example.com"]')).not.toBeNull();
    expect(body).toContain("The study guide stays open");
    expect(container.querySelector('a[href="/my/courses/3"]').textContent).toBe(
      "keep reading it"
    );
    expect(button("Re-take the assessment")).toBeUndefined();
    expect(button("Try again")).toBeUndefined();
    expect(body).not.toContain("No re-takes are left");
    expectNothingPerQuestion(text);
    expectNothingPerQuestion(body);
  });

  it("in the preview (no enrollment): Try again, no sitting count", async () => {
    const { retakes_remaining, ...preview } = FAILED;
    void retakes_remaining;
    const text = await failAnAttempt("text", preview);
    expect(button("Try again")).toBeDefined();
    expect(text).not.toContain("re-take left");
    expect(text).not.toContain("used all");
  });
});
