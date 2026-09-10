/**
 * 023c F1: the advice under a failed attempt follows the course's kind —
 * a study-guide course says re-read, a video course says re-watch. Nothing
 * per question appears either way (6.01.2 sub-ii).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import Assessment from "./Assessment.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function infoFor(lessonsKind) {
  return {
    course_code: "ATO",
    title: "Account Takeover",
    question_count: 1,
    passing_pct: "70",
    retakes_allowed: 2,
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

const FAILED = {
  status: "failed",
  score_pct: "0",
  passing_pct: "70",
  correct_count: 0,
  question_count: 1,
  retakes_allowed: 2,
  retakes_remaining: 1,
};

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

async function failAnAttempt(lessonsKind) {
  const api = {
    getAssessment: () => Promise.resolve(infoFor(lessonsKind)),
    start: () => Promise.resolve({ attempt_id: 7, status: "open" }),
    saveAnswers: () => Promise.resolve({}),
    submit: () => Promise.resolve(FAILED),
    getAttempt: () => Promise.resolve({ answers: {} }),
  };
  act(() => {
    root.render(<Assessment api={api} />);
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
