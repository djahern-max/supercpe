/**
 * 027: the video-only player seeks backward (it always could; now there is
 * a control for it), still refuses a forward seek past the furthest point
 * watched, and says what comes next when the video ends.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import Player from "./Player.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const LESSON = {
  lesson_id: "ASC842-PCX-01",
  title: "Lease Identification",
  video_url: "https://media.example/lesson.mp4",
  duration_seconds: 120,
  blocks: [
    { id: "b1", start_seconds: 0, end_seconds: 40 },
    { id: "b2", start_seconds: 40, end_seconds: 120 },
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
    },
  ],
};

const NEXT = {
  kind: "lesson",
  to: "/my/courses/1/lessons/8",
  label: "Next lesson: Lease Term",
  course: "/my/courses/1",
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

function render(props = {}) {
  act(() => {
    root.render(
      <MemoryRouter>
        <Player lesson={LESSON} gradeAnswer={() => Promise.resolve({})} {...props} />
      </MemoryRouter>
    );
  });
  return container.querySelector("video");
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

describe("Player seeking (027)", () => {
  it("allows a backward seek and offers a rewind control", () => {
    const video = render();
    watchTo(video, 30);
    video.currentTime = 10;
    fire(video, "seeking");
    fire(video, "seeked");
    expect(video.currentTime).toBe(10);

    const rewind = buttonNamed("Rewind 15 s");
    expect(rewind).toBeDefined();
    watchTo(video, 30);
    act(() => {
      rewind.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(video.currentTime).toBe(15);
  });

  it("still refuses a forward seek past the furthest point watched", () => {
    const video = render();
    watchTo(video, 30);
    video.currentTime = 90;
    fire(video, "seeking");
    fire(video, "seeked");
    expect(video.currentTime).toBe(30);
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
