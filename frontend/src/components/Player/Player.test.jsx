/**
 * 027: the video-only player seeks backward (it always could; now there is
 * a control for it) and says what comes next when the video ends.
 *
 * 031: forward seeking is open too, up to one ceiling — the earliest
 * review point whose question is still unanswered. Landing on it asks the
 * question; answering moves the ceiling; with every question answered the
 * whole timeline is open. 027's "refuses a forward seek past the furthest
 * point watched" is replaced by these, not deleted silently.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Player from "./Player.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Two review points: blocks 1 and 2 end at 40 s and 80 s, so they pause at
// 39.7 s and 79.7 s (039's REVIEW_PAUSE_LEAD_SECONDS).
const LESSON = {
  lesson_id: "ASC842-PCX-01",
  title: "Lease Identification",
  video_url: "https://media.example/lesson.mp4",
  duration_seconds: 120,
  blocks: [
    { id: "b1", start_seconds: 0, end_seconds: 40 },
    { id: "b2", start_seconds: 40, end_seconds: 80 },
    { id: "b3", start_seconds: 80, end_seconds: 120 },
  ],
  questions: [
    {
      question_key: "q-r01",
      after_block: 1,
      stem: "What conveys control?",
      choices: [
        { choice_key: "a", text: "Ownership" },
        { choice_key: "b", text: "The right to direct use" },
      ],
      answered: false,
    },
    {
      question_key: "q-r02",
      after_block: 2,
      stem: "When does the lease term start?",
      choices: [
        { choice_key: "a", text: "At signing" },
        { choice_key: "b", text: "At commencement" },
      ],
      answered: false,
    },
  ],
};

function withAnswered(...keys) {
  return {
    ...LESSON,
    questions: LESSON.questions.map((q) => ({
      ...q,
      answered: keys.includes(q.question_key),
    })),
  };
}

const NEXT = {
  kind: "lesson",
  to: "/my/courses/1/lessons/8",
  label: "Next lesson: Lease Term",
  course: "/my/courses/1",
};

let container;
let root;
// jsdom has no requestVideoFrameCallback, so the player falls back to
// requestAnimationFrame; frames run only when a test calls runFrame().
let frameQueue;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  frameQueue = new Map();
  let nextFrameId = 1;
  vi.stubGlobal("requestAnimationFrame", (callback) => {
    const id = nextFrameId++;
    frameQueue.set(id, callback);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id) => frameQueue.delete(id));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

/** Advance the stubbed playhead to `seconds` and deliver one frame. */
function runFrame(video, seconds) {
  video.currentTime = seconds;
  const callbacks = Array.from(frameQueue.values());
  frameQueue.clear();
  act(() => callbacks.forEach((callback) => callback(performance.now())));
}

function render(props = {}) {
  act(() => {
    root.render(
      <MemoryRouter>
        <Player lesson={LESSON} gradeAnswer={() => Promise.resolve({})} {...props} />
      </MemoryRouter>
    );
  });
  const video = container.querySelector("video");
  // jsdom has no media pipeline; the player only needs these to exist.
  let paused = true;
  Object.defineProperty(video, "paused", {
    get: () => paused,
    configurable: true,
  });
  video.pause = vi.fn(() => {
    paused = true;
  });
  video.play = vi.fn(() => {
    paused = false;
    return Promise.resolve();
  });
  return video;
}

/** Start playback the way the media element reports it. */
function play(video) {
  video.play();
  fire(video, "play");
}

function fire(video, type) {
  act(() => {
    video.dispatchEvent(new Event(type));
  });
}

/** Play up to `seconds` without crossing a review point. */
function watchTo(video, seconds) {
  video.currentTime = seconds;
  fire(video, "timeupdate");
}

function buttonNamed(text) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === text
  );
}

function click(button) {
  act(() => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

/** A user seek: set the target, then the media element's two events. */
function seek(video, seconds) {
  video.currentTime = seconds;
  fire(video, "seeking");
  fire(video, "seeked");
}

const dialog = () => container.querySelector('[role="dialog"]');

/** Answer the open question and Continue; `graded` is the server's verdict. */
async function answer(choiceText, graded) {
  click(buttonNamed(choiceText));
  await act(async () => {
    buttonNamed("Submit").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
  });
  expect(dialog().textContent).toContain(graded.correct ? "Correct" : "Not quite");
}

const CORRECT = { correct: true, feedback: "Right.", correct_choice_key: "b" };
const WRONG = { correct: false, feedback: "Not this one.", correct_choice_key: "b" };

describe("Player seeking (027, 031)", () => {
  it("allows a backward seek and offers a rewind control", () => {
    const video = render();
    watchTo(video, 30);
    seek(video, 10);
    expect(video.currentTime).toBe(10);
    expect(dialog()).toBeNull();

    const rewind = buttonNamed("Rewind 15 s");
    expect(rewind).toBeDefined();
    watchTo(video, 30);
    click(rewind);
    expect(video.currentTime).toBe(15);
  });

  it("clamps a forward seek past the first unanswered review point to it and asks", () => {
    const video = render();
    watchTo(video, 10);
    seek(video, 90);
    expect(video.currentTime).toBe(39.7);
    expect(dialog().textContent).toContain("What conveys control?");
    expect(video.pause).toHaveBeenCalled();
    expect(container.innerHTML).not.toContain("is_correct");
  });

  it("honours a forward seek within the ceiling, past the furthest point watched", () => {
    const video = render();
    watchTo(video, 10);
    seek(video, 30);
    expect(video.currentTime).toBe(30);
    expect(dialog()).toBeNull();
    // Arrow keys seek within the same range.
    act(() => {
      container.firstChild.dispatchEvent(
        new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })
      );
    });
    expect(video.currentTime).toBe(35);
    act(() => {
      container.firstChild.dispatchEvent(
        new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })
      );
    });
    expect(video.currentTime).toBe(39.7);
    fire(video, "seeking");
    fire(video, "seeked");
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("Forward 15 s keeps playing from early on and asks when it lands on the ceiling", () => {
    const video = render();
    const forward = buttonNamed("Forward 15 s");
    expect(forward).toBeDefined();
    watchTo(video, 10);
    click(forward);
    fire(video, "seeking");
    fire(video, "seeked");
    expect(video.currentTime).toBe(25);
    expect(dialog()).toBeNull();

    watchTo(video, 35);
    click(forward);
    fire(video, "seeking");
    fire(video, "seeked");
    expect(video.currentTime).toBe(39.7);
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("after answering the first question a forward seek clamps at the second", async () => {
    const video = render({ gradeAnswer: () => Promise.resolve(CORRECT) });
    seek(video, 90);
    expect(video.currentTime).toBe(39.7);
    await answer("The right to direct use", CORRECT);
    click(buttonNamed("Continue"));
    expect(dialog()).toBeNull();
    expect(video.play).toHaveBeenCalled();

    seek(video, 60);
    expect(video.currentTime).toBe(60);
    expect(dialog()).toBeNull();

    seek(video, 110);
    expect(video.currentTime).toBe(79.7);
    expect(dialog().textContent).toContain("When does the lease term start?");
    // The bar shows the first point as answered, the second not yet.
    const ticks = container.querySelectorAll('[title^="Review question"]');
    expect(Array.from(ticks).map((t) => t.getAttribute("title"))).toEqual([
      "Review question (answered)",
      "Review question",
    ]);
  });

  it("with every question answered on load, a seek to the end is honoured", () => {
    const video = render({ lesson: withAnswered("q-r01", "q-r02") });
    seek(video, 119);
    expect(video.currentTime).toBe(119);
    expect(dialog()).toBeNull();
  });

  it("resume lands on the ceiling, not past it, and asks", () => {
    const video = render({
      lesson: withAnswered("q-r01"),
      initialFurthestSeconds: 100,
    });
    Object.defineProperty(video, "duration", { value: 120, configurable: true });
    fire(video, "loadedmetadata");
    expect(video.currentTime).toBe(79.7);
    fire(video, "seeking");
    fire(video, "seeked");
    expect(dialog().textContent).toContain("When does the lease term start?");
  });

  it("a wrong answer's re-watch link seeks to the block start and resumes", async () => {
    const video = render({ gradeAnswer: () => Promise.resolve(WRONG) });
    seek(video, 90);
    await answer("Ownership", WRONG);
    click(buttonNamed("Re-watch this section"));
    expect(dialog()).toBeNull();
    expect(video.currentTime).toBe(0);
    expect(video.play).toHaveBeenCalled();
    // The question is on record as answered, so the ceiling moved on: a
    // seek past 40 now clamps at the second point.
    seek(video, 100);
    expect(video.currentTime).toBe(79.7);
  });
});

describe("Player end panel (027)", () => {
  it("shows the derived next step when the video ends", () => {
    const video = render({ nextStep: NEXT, reviewRemaining: 0 });
    expect(container.querySelector('[aria-label="Lesson finished"]')).toBeNull();
    fire(video, "ended");
    const panel = container.querySelector('[aria-label="Lesson finished"]');
    expect(panel.textContent).toContain("Lesson finished");
    const link = panel.querySelector('a[href="/my/courses/1/lessons/8"]');
    expect(link.textContent).toBe("Next lesson: Lease Term");
  });

  it("asks the remaining review questions first", () => {
    const video = render({ nextStep: NEXT, reviewRemaining: 1 });
    fire(video, "ended");
    const panel = container.querySelector('[aria-label="Lesson finished"]');
    expect(panel.textContent).toContain("1 review question is still unanswered");
    expect(panel.querySelector("a")).toBeNull();
    act(() => {
      buttonNamed("Answer the review questions").dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("What conveys control?");
    // No answer key on the way in.
    expect(container.innerHTML).not.toContain("is_correct");
  });

  it("says nothing more than the end without a next step (the preview)", () => {
    const video = render();
    fire(video, "ended");
    const panel = container.querySelector('[aria-label="Lesson finished"]');
    expect(panel.textContent).toContain("End of this lesson.");
    expect(panel.querySelector("a")).toBeNull();
  });
});

// 039: block 1 ends at 30 s (pause 29.7), block 2 ends at 60 s (pause 59.7).
const LESSON_30 = {
  ...LESSON,
  duration_seconds: 90,
  blocks: [
    { id: "b1", start_seconds: 0, end_seconds: 30 },
    { id: "b2", start_seconds: 30, end_seconds: 60 },
    { id: "b3", start_seconds: 60, end_seconds: 90 },
  ],
};

describe("Player review pauses in the silence (039)", () => {
  it("pauses at end_seconds minus the lead on a frame, without waiting for timeupdate", () => {
    const video = render({ lesson: LESSON_30 });
    play(video);
    runFrame(video, 29.6);
    expect(dialog()).toBeNull();
    runFrame(video, 29.7);
    expect(video.pause).toHaveBeenCalled();
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("pauses a block shorter than the lead at its start, never before it", () => {
    const lesson = {
      ...LESSON,
      duration_seconds: 40,
      blocks: [
        { id: "b1", start_seconds: 0, end_seconds: 10 },
        { id: "b2", start_seconds: 10, end_seconds: 10.2 },
        { id: "b3", start_seconds: 10.2, end_seconds: 40 },
      ],
      questions: [{ ...LESSON.questions[0], after_block: 2 }],
    };
    const video = render({ lesson });
    play(video);
    runFrame(video, 9.9);
    expect(dialog()).toBeNull();
    runFrame(video, 10);
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("resumes after Continue at the pause time and does not re-ask on the way on", async () => {
    const video = render({
      lesson: LESSON_30,
      gradeAnswer: () => Promise.resolve(CORRECT),
    });
    play(video);
    // A frame can land just past the pause time; resume still starts at it.
    runFrame(video, 29.75);
    await answer("The right to direct use", CORRECT);
    click(buttonNamed("Continue"));
    expect(video.currentTime).toBe(29.7);
    expect(video.play).toHaveBeenCalled();
    fire(video, "play");
    runFrame(video, 31);
    watchTo(video, 31);
    expect(dialog()).toBeNull();
  });

  it("asks again after seeking back before the point and playing through it", async () => {
    const video = render({
      lesson: LESSON_30,
      gradeAnswer: () => Promise.resolve(CORRECT),
    });
    play(video);
    runFrame(video, 29.7);
    await answer("The right to direct use", CORRECT);
    click(buttonNamed("Continue"));
    fire(video, "play");
    runFrame(video, 31);
    expect(dialog()).toBeNull();
    seek(video, 20);
    runFrame(video, 25);
    expect(dialog()).toBeNull();
    runFrame(video, 29.7);
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("clamps a forward seek to the pause time and asks", () => {
    const video = render({ lesson: LESSON_30 });
    seek(video, 60);
    expect(video.currentTime).toBe(29.7);
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("Forward 15 s from 20 lands on the pause time and asks", () => {
    const video = render({ lesson: LESSON_30 });
    watchTo(video, 20);
    click(buttonNamed("Forward 15 s"));
    fire(video, "seeking");
    fire(video, "seeked");
    expect(video.currentTime).toBe(29.7);
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("Re-watch this section still seeks to the block's start_seconds", async () => {
    let verdict = CORRECT;
    const video = render({
      lesson: LESSON_30,
      gradeAnswer: () => Promise.resolve(verdict),
    });
    seek(video, 60);
    await answer("The right to direct use", CORRECT);
    click(buttonNamed("Continue"));
    verdict = WRONG;
    seek(video, 80);
    expect(video.currentTime).toBe(59.7);
    await answer("At signing", WRONG);
    click(buttonNamed("Re-watch this section"));
    expect(video.currentTime).toBe(30);
  });

  it("resume on load past an unanswered point lands on its pause time and asks", () => {
    const video = render({ lesson: LESSON_30, initialFurthestSeconds: 45 });
    Object.defineProperty(video, "duration", { value: 90, configurable: true });
    fire(video, "loadedmetadata");
    expect(video.currentTime).toBe(29.7);
    fire(video, "seeking");
    fire(video, "seeked");
    expect(dialog().textContent).toContain("What conveys control?");
  });

  it("keeps the tick at end_seconds", () => {
    render({ lesson: LESSON_30 });
    const tick = container.querySelector('[title^="Review question"]');
    expect(tick.style.left).toBe(`${(30 / 90) * 100}%`);
  });
});

describe("Player full screen (039)", () => {
  afterEach(() => {
    delete document.fullscreenEnabled;
    delete document.fullscreenElement;
    delete HTMLElement.prototype.requestFullscreen;
    delete window.screen.orientation;
  });

  function enableFullscreen() {
    Object.defineProperty(document, "fullscreenEnabled", {
      value: true,
      configurable: true,
    });
    const requestFullscreen = vi.fn(() => Promise.resolve());
    HTMLElement.prototype.requestFullscreen = requestFullscreen;
    return requestFullscreen;
  }

  it("offers no button where the Fullscreen API is unavailable (iPhone)", () => {
    Object.defineProperty(document, "fullscreenEnabled", {
      value: false,
      configurable: true,
    });
    render();
    expect(buttonNamed("Full screen")).toBeUndefined();
  });

  it("puts the wrapper, not the video, into full screen", async () => {
    const requestFullscreen = enableFullscreen();
    const video = render();
    await act(async () => {
      buttonNamed("Full screen").dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    expect(requestFullscreen).toHaveBeenCalledTimes(1);
    const target = requestFullscreen.mock.contexts[0];
    expect(target).toBe(container.firstChild);
    expect(target).not.toBe(video);
    expect(target.contains(video)).toBe(true);
  });

  it("flips its label on fullscreenchange", () => {
    enableFullscreen();
    render();
    Object.defineProperty(document, "fullscreenElement", {
      value: container.firstChild,
      configurable: true,
    });
    act(() => document.dispatchEvent(new Event("fullscreenchange")));
    expect(buttonNamed("Exit full screen")).toBeDefined();
    Object.defineProperty(document, "fullscreenElement", {
      value: null,
      configurable: true,
    });
    act(() => document.dispatchEvent(new Event("fullscreenchange")));
    expect(buttonNamed("Full screen")).toBeDefined();
  });

  it("ignores a rejected orientation lock", async () => {
    enableFullscreen();
    const lock = vi.fn(() => Promise.reject(new Error("not allowed")));
    Object.defineProperty(window.screen, "orientation", {
      value: { lock },
      configurable: true,
    });
    render();
    await act(async () => {
      buttonNamed("Full screen").dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    expect(lock).toHaveBeenCalledWith("landscape");
  });
});
