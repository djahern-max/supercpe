/**
 * 023c D2: review-question feedback survives the unlock refetch. The
 * lesson page refetches the payload after every graded answer (that is
 * how the next section opens); the verdict and feedback must still be on
 * screen afterwards, for a right and for a wrong answer (5.01.2.2).
 *
 * 023c F3: a section whose markdown opens with its own title renders the
 * title once.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import Reader from "./Reader.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const QUESTION = {
  question_key: "q-r01",
  after_section: "sec-01",
  stem: "Which criterion identifies a lease?",
  choices: [
    { choice_key: "a", text: "Ownership" },
    { choice_key: "b", text: "Control of an identified asset" },
  ],
  answered: false,
};

function lessonPayload({ unlocked = false, answered = false } = {}) {
  return {
    lesson_id: "ASC842-GDE-01",
    title: "Identifying a Lease Under ASC 842",
    kind: "text",
    word_count: 64,
    sections: [
      {
        section_key: "sec-01",
        role: "body",
        title: "Identifying a Lease",
        position: 1,
        locked: false,
        markdown: "# Identifying a Lease\n\nA contract is a lease when it conveys control.",
        question_keys: ["q-r01"],
      },
      {
        section_key: "sec-02",
        role: "body",
        title: "Identified Asset",
        position: 2,
        locked: !unlocked,
        markdown: unlocked ? "# Overview\n\nAn asset is identified when…" : null,
        question_keys: [],
      },
    ],
    media: [],
    questions: [{ ...QUESTION, answered }],
  };
}

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(lesson, props) {
  act(() => {
    root.render(<Reader lesson={lesson} {...props} />);
  });
}

function click(button) {
  act(() => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

function choiceButton(text) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === text
  );
}

async function answerAndRefetch(verdict) {
  // What MyLesson does: grade, then reload the payload. The reload
  // resolves to a *new object* for the same lesson with the next section
  // open and the question marked answered — exactly the state that used
  // to wipe the verdict.
  let refetched = null;
  const props = {
    gradeAnswer: () => Promise.resolve(verdict),
    onAnswered: () => {
      refetched = lessonPayload({ unlocked: true, answered: true });
    },
  };
  render(lessonPayload(), props);
  expect(container.textContent).toContain("Answer the review question above");

  click(choiceButton("Control of an identified asset"));
  await act(async () => {
    await Promise.resolve();
  });
  expect(refetched).not.toBeNull();
  render(refetched, props);
  await act(async () => {
    await Promise.resolve();
  });
  return refetched;
}

describe("Reader feedback across the unlock refetch (023c D2)", () => {
  it("keeps a correct verdict and its feedback on screen", async () => {
    await answerAndRefetch({
      correct: true,
      correct_choice_key: "b",
      feedback: "Right: control of an identified asset is the test.",
    });
    // The refetch really did open the next section...
    expect(container.textContent).toContain("An asset is identified when");
    expect(container.textContent).not.toContain("Answer the review question above");
    // ...and the feedback is still there, not the "answered earlier" note.
    expect(container.textContent).toContain("Correct.");
    expect(container.textContent).toContain(
      "Right: control of an identified asset is the test."
    );
    expect(container.textContent).not.toContain("You answered this question earlier");
  });

  it("keeps an incorrect verdict and its feedback on screen", async () => {
    await answerAndRefetch({
      correct: false,
      correct_choice_key: "a",
      feedback: "Not ownership — control is what matters.",
    });
    expect(container.textContent).toContain("An asset is identified when");
    expect(container.textContent).toContain("Not quite.");
    expect(container.textContent).toContain("Not ownership — control is what matters.");
    expect(container.textContent).not.toContain("You answered this question earlier");
  });

  it("starts over for a different lesson", async () => {
    await answerAndRefetch({ correct: true, correct_choice_key: "b", feedback: "Yes." });
    render({ ...lessonPayload({ unlocked: true, answered: true }), lesson_id: "OTHER-02" }, {
      gradeAnswer: () => Promise.resolve({}),
    });
    expect(container.textContent).not.toContain("Correct.");
    expect(container.textContent).toContain("You answered this question earlier");
  });
});

describe("Section titles (023c F3)", () => {
  it("renders a title once when the markdown opens with the same heading", () => {
    render(lessonPayload({ unlocked: true }), { gradeAnswer: () => Promise.resolve({}) });
    const headings = Array.from(container.querySelectorAll("h1, h2, h3")).map(
      (h) => h.textContent
    );
    // "Identifying a Lease" appears in the contents list (a button, not a
    // heading) and once as the section heading — not again as the
    // markdown's H1.
    expect(headings.filter((h) => h === "Identifying a Lease")).toHaveLength(1);
    // The only H1 left is the one that was not a repeat of its title.
    expect(Array.from(container.querySelectorAll("h1")).map((h) => h.textContent)).toEqual([
      "Overview",
    ]);
    // A heading that says something else is kept alongside the title.
    expect(headings.filter((h) => h === "Identified Asset")).toHaveLength(1);
    expect(headings).toContain("Overview");
    // The section text itself is intact.
    expect(container.textContent).toContain("A contract is a lease when it conveys control.");
  });
});
