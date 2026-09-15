/**
 * 023c D2: review-question feedback survives the unlock refetch. The
 * lesson page refetches the payload after every graded answer (that is
 * how the next section opens); the verdict and feedback must still be on
 * screen afterwards, for a right and for a wrong answer (5.01.2.2) — and,
 * since 027, after leaving the section and coming back.
 *
 * 023c F3: a section whose markdown opens with its own title renders the
 * title once.
 *
 * 027: the reader is a stepper. One section at a time; a locked entry in
 * the contents is a title and never a body; Continue is disabled until
 * every question placed after the section is answered; the progress line
 * counts body sections only; the URL carries the position; nothing that
 * looks like an answer key reaches the DOM before grading; a finished
 * lesson shows the next step; a supplemental clip has native controls,
 * no seek lock, and says where to go when it ends.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
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

const FRONT_MATTER = "## How this course works\n\nRead it in order.";
const BODY_ONE = "# Identifying a Lease\n\nA contract is a lease when it conveys control.";
const BODY_TWO = "# Overview\n\nAn asset is identified when…";
const BODY_THREE = "# Right to Direct Use\n\nThe customer directs the use.";
const GLOSSARY = "# Glossary\n\nTerms used in this guide.";

function lessonPayload({ unlocked = false, answered = false, media = [] } = {}) {
  return {
    lesson_id: "ASC842-GDE-01",
    title: "Identifying a Lease Under ASC 842",
    kind: "text",
    word_count: 64,
    sections: [
      {
        section_key: "sec-00",
        role: "front_matter",
        title: "How this course works",
        position: 0,
        locked: false,
        markdown: FRONT_MATTER,
        question_keys: [],
      },
      {
        section_key: "sec-01",
        role: "body",
        title: "Identifying a Lease",
        position: 1,
        locked: false,
        markdown: BODY_ONE,
        question_keys: ["q-r01"],
      },
      {
        section_key: "sec-02",
        role: "body",
        title: "Identified Asset",
        position: 2,
        locked: !unlocked,
        markdown: unlocked ? BODY_TWO : null,
        question_keys: [],
      },
      {
        section_key: "sec-03",
        role: "body",
        title: "Right to Direct Use",
        position: 3,
        locked: !unlocked,
        markdown: unlocked ? BODY_THREE : null,
        question_keys: [],
      },
      {
        section_key: "sec-90",
        role: "glossary",
        title: "Glossary",
        position: 90,
        locked: false,
        markdown: GLOSSARY,
        question_keys: [],
      },
    ],
    media,
    questions: [{ ...QUESTION, answered }],
  };
}

const CLIP = {
  media_key: "vid-01",
  after_section: "sec-01",
  url: "https://media.example/ex-01.mp4",
  duration_seconds: 90,
};

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

/** The router's current search string, written into the DOM to read. */
function LocationProbe() {
  const { search } = useLocation();
  return <output id="location">{search}</output>;
}

const location = () => container.querySelector("#location").textContent;

// A MemoryRouter reads `initialEntries` once, so a render at a different
// path is a fresh router (the key); a render at the same path keeps the
// router's history and the Reader's state, which is what the refetch
// tests need.
function render(lesson, props = {}, path = "/lesson") {
  act(() => {
    root.render(
      <MemoryRouter key={path} initialEntries={[path]}>
        <Reader gradeAnswer={() => Promise.resolve({})} lesson={lesson} {...props} />
        <LocationProbe />
      </MemoryRouter>
    );
  });
}

function click(button) {
  act(() => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

function buttonNamed(text) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === text
  );
}

const continueButton = () => buttonNamed("Continue");
const pane = () => container.querySelector("article");
const contents = () => container.querySelector('nav[aria-label="Course contents"]');

const flush = () =>
  act(async () => {
    await Promise.resolve();
  });

const AT_SEC_01 = "/lesson?section=sec-01";

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
  render(lessonPayload(), props, AT_SEC_01);
  expect(continueButton().disabled).toBe(true);

  click(buttonNamed("Control of an identified asset"));
  await flush();
  expect(refetched).not.toBeNull();
  render(refetched, props, AT_SEC_01);
  await flush();
  return { refetched, props };
}

describe("Reader feedback across the unlock refetch (023c D2)", () => {
  it("keeps a correct verdict and its feedback on screen", async () => {
    await answerAndRefetch({
      correct: true,
      correct_choice_key: "b",
      feedback: "Right: control of an identified asset is the test.",
    });
    // The refetch really did open the next section: Continue is live...
    expect(continueButton().disabled).toBe(false);
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
    expect(container.textContent).toContain("Not quite.");
    expect(container.textContent).toContain("Not ownership — control is what matters.");
    expect(container.textContent).not.toContain("You answered this question earlier");
  });

  it("keeps the verdict after leaving the section and coming back", async () => {
    await answerAndRefetch({ correct: true, correct_choice_key: "b", feedback: "Yes." });
    click(continueButton());
    expect(pane().textContent).toContain("An asset is identified when");
    expect(pane().textContent).not.toContain("Yes.");
    click(buttonNamed("Previous"));
    expect(pane().textContent).toContain("Correct.");
    expect(pane().textContent).toContain("Yes.");
  });

  it("starts over for a different lesson", async () => {
    await answerAndRefetch({ correct: true, correct_choice_key: "b", feedback: "Yes." });
    render(
      { ...lessonPayload({ unlocked: true, answered: true }), lesson_id: "OTHER-02" },
      { gradeAnswer: () => Promise.resolve({}) },
      AT_SEC_01
    );
    expect(container.textContent).not.toContain("Correct.");
    expect(container.textContent).toContain("You answered this question earlier");
  });
});

describe("Section titles (023c F3)", () => {
  it("renders a title once when the markdown opens with the same heading", () => {
    render(lessonPayload({ unlocked: true, answered: true }), {}, AT_SEC_01);
    const headings = () =>
      Array.from(pane().querySelectorAll("h1, h2, h3")).map((h) => h.textContent);
    // "Identifying a Lease" appears in the contents list (a button, not a
    // heading) and once as the section heading — not again as the
    // markdown's H1.
    expect(headings().filter((h) => h === "Identifying a Lease")).toHaveLength(1);
    expect(pane().querySelector("h1")).toBeNull();
    expect(pane().textContent).toContain("A contract is a lease when it conveys control.");
    // A heading that says something else is kept alongside the title.
    click(continueButton());
    expect(headings()).toContain("Identified Asset");
    expect(headings()).toContain("Overview");
  });
});

describe("Reader as a section stepper (027)", () => {
  it("renders exactly one body section's markdown at a time", () => {
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-01");
    expect(pane().textContent).toContain("A contract is a lease when it conveys control.");
    expect(pane().textContent).not.toContain("An asset is identified when");
    expect(pane().textContent).not.toContain("The customer directs the use.");
    expect(pane().textContent).not.toContain("Terms used in this guide.");
    // Every section is listed, the reference material apart.
    const entries = Array.from(contents().querySelectorAll("button")).map(
      (b) => b.textContent
    );
    expect(entries.join(" | ")).toContain("How this course works");
    expect(entries.join(" | ")).toContain("Right to Direct Use");
    expect(contents().textContent).toContain("Reference");
    expect(contents().textContent).toContain("Glossary");
  });

  it("lists a locked section by title only and never its body", () => {
    render(lessonPayload(), {}, "/lesson?section=sec-01");
    const locked = Array.from(contents().querySelectorAll("button")).find((b) =>
      b.textContent.startsWith("Identified Asset")
    );
    expect(locked.disabled).toBe(true);
    expect(locked.textContent).toContain("Locked");
    // Reaching it by URL shows the title and the reason, nothing else.
    render(lessonPayload(), {}, "/lesson?section=sec-02");
    expect(pane().textContent).toContain("Identified Asset");
    expect(pane().textContent).toContain("Answer the review question after the previous section");
    expect(container.innerHTML).not.toContain("An asset is identified");
    expect(continueButton().disabled).toBe(true);
  });

  it("front matter renders first, with the navigation instructions", () => {
    render(lessonPayload());
    expect(pane().textContent).toContain("Start here");
    expect(pane().textContent).toContain("How this course works");
    expect(pane().textContent).toContain("Read it in order.");
    expect(location()).toBe("");
    click(continueButton());
    expect(location()).toBe("?section=sec-01");
  });

  it("disables Continue until every inline question is answered", () => {
    render(lessonPayload(), {}, "/lesson?section=sec-01");
    expect(pane().textContent).toContain("Which criterion identifies a lease?");
    expect(continueButton().disabled).toBe(true);
    expect(pane().textContent).toContain("Answer the review question above to continue.");
    // The server says it is answered (a later visit): Continue is live.
    render(lessonPayload({ unlocked: true, answered: true }), {}, "/lesson?section=sec-01");
    expect(continueButton().disabled).toBe(false);
    click(continueButton());
    expect(location()).toBe("?section=sec-02");
    expect(pane().textContent).toContain("Section 2 of 3");
  });

  it("counts body sections only in the progress line", () => {
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-00");
    expect(pane().textContent).toContain("Start here");
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-01");
    expect(pane().textContent).toContain("Section 1 of 3");
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-03");
    expect(pane().textContent).toContain("Section 3 of 3");
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-90");
    expect(pane().textContent).toContain("Reference");
    expect(pane().textContent).toContain("Terms used in this guide.");
    expect(buttonNamed("Back to the guide")).toBeDefined();
  });

  it("round-trips the position through the URL", () => {
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=sec-03");
    expect(location()).toBe("?section=sec-03");
    expect(pane().textContent).toContain("The customer directs the use.");
    const entry = Array.from(contents().querySelectorAll("button")).find((b) =>
      b.textContent.startsWith("Identifying a Lease")
    );
    click(entry);
    expect(location()).toBe("?section=sec-01");
    expect(pane().textContent).toContain("A contract is a lease");
    // An unknown key falls back to the derived position, not a blank pane.
    render(lessonPayload({ unlocked: true }), {}, "/lesson?section=nope");
    expect(pane().textContent).toContain("Start here");
  });

  it("lands on the first section not yet read when the URL names none", () => {
    // The gate after sec-01 is passed and sec-02 is open: resume there.
    render(lessonPayload({ unlocked: true, answered: true }));
    expect(pane().textContent).toContain("An asset is identified when");
    const states = Array.from(contents().querySelectorAll("li")).map(
      (li) => li.textContent
    );
    expect(states.find((s) => s.startsWith("Identifying a Lease"))).toContain("Read");
  });

  it("never renders an answer key, and feedback only after grading", async () => {
    const feedback = "Right: control of an identified asset is the test.";
    render(
      lessonPayload(),
      {
        gradeAnswer: () =>
          Promise.resolve({ correct: true, correct_choice_key: "b", feedback }),
      },
      "/lesson?section=sec-01"
    );
    for (const key of ["is_correct", "correct_choice_key", "feedback"]) {
      expect(container.innerHTML).not.toContain(key);
    }
    expect(container.textContent).not.toContain(feedback);
    click(buttonNamed("Control of an identified asset"));
    await flush();
    expect(container.textContent).toContain(feedback);
  });
});

describe("Completion card (027)", () => {
  const assessment = {
    kind: "assessment",
    to: "/my/courses/1/assessment",
    label: "Take the qualified assessment",
    course: "/my/courses/1",
  };

  it("appears after the last body section once every question is answered", () => {
    render(
      lessonPayload({ unlocked: true, answered: true }),
      { nextStep: assessment },
      "/lesson?section=sec-03"
    );
    const card = container.querySelector('section[aria-label="Next step"]');
    expect(card.textContent).toContain("You've finished the study guide");
    const primary = card.querySelector('a[href="/my/courses/1/assessment"]');
    expect(primary.textContent).toBe("Take the qualified assessment");
    expect(card.querySelector('a[href="/my/courses/1"]').textContent).toBe(
      "Back to the course page"
    );
  });

  it("does not appear while a question is unanswered, nor before the last section", () => {
    render(lessonPayload({ unlocked: true }), { nextStep: assessment }, "/lesson?section=sec-03");
    expect(container.querySelector('section[aria-label="Next step"]')).toBeNull();
    render(
      lessonPayload({ unlocked: true, answered: true }),
      { nextStep: assessment },
      "/lesson?section=sec-02"
    );
    expect(container.querySelector('section[aria-label="Next step"]')).toBeNull();
  });

  it("names the next lesson when one remains", () => {
    render(
      lessonPayload({ unlocked: true, answered: true }),
      {
        nextStep: {
          kind: "lesson",
          to: "/my/courses/1/lessons/9",
          label: "Next lesson: Lease Term",
          course: "/my/courses/1",
        },
      },
      "/lesson?section=sec-03"
    );
    const card = container.querySelector('section[aria-label="Next step"]');
    expect(card.textContent).toContain("You've finished this lesson");
    expect(card.querySelector('a[href="/my/courses/1/lessons/9"]').textContent).toBe(
      "Next lesson: Lease Term"
    );
    expect(card.textContent).not.toContain("qualified assessment");
  });
});

describe("Supplemental clips (027)", () => {
  it("has native controls and no seek lock", () => {
    render(lessonPayload({ media: [CLIP] }), {}, "/lesson?section=sec-01");
    const video = container.querySelector("video");
    expect(video.hasAttribute("controls")).toBe(true);
    // A seek anywhere stands: nothing undoes it once it settles.
    video.currentTime = 42;
    act(() => {
      video.dispatchEvent(new Event("seeking"));
      video.dispatchEvent(new Event("seeked"));
    });
    expect(video.currentTime).toBe(42);
    expect(container.textContent).not.toContain("Continue reading");
  });

  it("says where to go when it ends", () => {
    render(lessonPayload({ media: [CLIP] }), {}, "/lesson?section=sec-01");
    const video = container.querySelector("video");
    act(() => {
      video.dispatchEvent(new Event("ended"));
    });
    const affordance = buttonNamed("Continue reading");
    expect(affordance).toBeDefined();
    // The question after this section is still open: stay here, at it.
    click(affordance);
    expect(location()).toBe("?section=sec-01");
    // Once the gate is clear, the same affordance opens the next section.
    render(lessonPayload({ media: [CLIP], unlocked: true, answered: true }), {}, "/lesson?section=sec-01");
    act(() => {
      container.querySelector("video").dispatchEvent(new Event("ended"));
    });
    click(buttonNamed("Continue reading"));
    expect(location()).toBe("?section=sec-02");
  });
});

// --- 037: where the participant is -----------------------------------------
//
// The reader used to say "START HERE" over a bar that never moved: the bar
// counted sections this session had scrolled past, so it sat at zero on
// the section the participant was actually on, and passing a review gate
// did not move it. Now the line names the lesson and the section, and the
// bar is the gate.

/** The 037 payload: a server that says where this lesson sits. */
function positionedPayload(overrides = {}, lessonOverrides = {}) {
  return {
    ...lessonPayload(overrides),
    course_title: "Identifying a Lease Under ASC 842",
    lesson_position: 4,
    lesson_count: 6,
    // Deliberately not the three body sections this fixture renders: the
    // counts are the server's figures for the whole lesson, and the line
    // must show them rather than something counted from `sections`.
    section_count: 7,
    sections_completed: 2,
    ...lessonOverrides,
  };
}

const bar = () => container.querySelector('[role="progressbar"]');
const fill = () => bar().firstElementChild.style.width;

describe("Reader position indicator (037)", () => {
  it("names the lesson and the section from the payload", () => {
    render(positionedPayload(), {}, "/lesson?section=sec-02");
    expect(pane().textContent).toContain("Lesson 4 of 6 · Section 2 of 7");
  });

  it("updates the section position when another section is selected", () => {
    render(positionedPayload({ unlocked: true }), {}, AT_SEC_01);
    expect(pane().textContent).toContain("Lesson 4 of 6 · Section 1 of 7");

    click(
      Array.from(contents().querySelectorAll("button")).find((b) =>
        b.textContent.startsWith("Right to Direct Use")
      )
    );
    expect(pane().textContent).toContain("Lesson 4 of 6 · Section 3 of 7");

    click(
      Array.from(contents().querySelectorAll("button")).find((b) =>
        b.textContent.startsWith("How this course works")
      )
    );
    expect(pane().textContent).toContain("Lesson 4 of 6 · Start here");
  });

  it("fills the bar from the server's completed sections", () => {
    render(positionedPayload(), {}, AT_SEC_01);
    expect(bar().getAttribute("aria-label")).toBe("2 of 7 sections complete");
    expect(bar().getAttribute("aria-valuenow")).toBe("2");
    expect(bar().getAttribute("aria-valuemax")).toBe("7");
    // 2/7 of the track, not 0 — which is what the old "sections scrolled
    // past" count showed on the section the participant was reading.
    expect(fill()).toBe(`${(2 / 7) * 100}%`);
  });

  it("advances the bar when a review gate is passed, without a reload", async () => {
    // Nothing answered, nothing complete, and no refetch in this test:
    // the bar must move on the strength of the verdict alone.
    const payload = positionedPayload({}, { sections_completed: 0 });
    render(payload, {
      gradeAnswer: () =>
        Promise.resolve({
          correct: true,
          correct_choice_key: "b",
          feedback: "Right.",
        }),
    }, AT_SEC_01);
    expect(bar().getAttribute("aria-label")).toBe("0 of 7 sections complete");

    click(buttonNamed("Control of an identified asset"));
    await flush();
    expect(bar().getAttribute("aria-label")).toBe("1 of 7 sections complete");
    expect(bar().getAttribute("aria-valuenow")).toBe("1");
  });

  it("matches the server after a reload", () => {
    // A fresh mount with no session verdicts — what a reload is — shows
    // exactly what the server counted.
    render(positionedPayload({}, { sections_completed: 5 }), {}, AT_SEC_01);
    expect(bar().getAttribute("aria-label")).toBe("5 of 7 sections complete");
  });

  it("still reads sensibly for a payload without the position values", () => {
    render(lessonPayload(), {}, "/lesson?section=sec-02");
    expect(pane().textContent).toContain("Section 2 of 3");
    expect(pane().textContent).not.toContain("Lesson");
  });
});
