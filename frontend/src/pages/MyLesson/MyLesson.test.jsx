/**
 * 037: the lesson page's breadcrumb. It read "My courses / course /
 * lesson" — two literal placeholders — while the enrollment detail it
 * already fetched carried the course title and every lesson's position
 * and title. These pin the real names, for a text lesson and a video
 * one, and pin that nothing is read out of the URL.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MyLesson from "./MyLesson.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getMyEnrollment: vi.fn(),
  getMyReadLesson: vi.fn(),
  getMyPlayLesson: vi.fn(),
  gradeMyReview: vi.fn(),
  putMyProgress: vi.fn(),
  searchMyCourse: vi.fn(),
  getMyGlossary: vi.fn(),
}));

vi.mock("../../api/my", () => api);

const READ_PACKAGE_ID = 71;
const PLAY_PACKAGE_ID = 72;

function enrollment() {
  return {
    enrollment_id: 12,
    course_code: "ASC842-GDE",
    title: "Identifying a Lease Under ASC 842",
    status: "active",
    completion: null,
    open_attempt_id: null,
    assessment_available: false,
    failed_attempts: 0,
    retakes_remaining: null,
    lessons: [
      {
        package_id: READ_PACKAGE_ID,
        lesson_id: "ASC842-GDE-04",
        kind: "text",
        position: 4,
        title: "Verifying the output",
        review_answered: 0,
        review_total: 2,
        done: false,
      },
      {
        package_id: PLAY_PACKAGE_ID,
        lesson_id: "ASC842-GDE-05",
        kind: "video",
        position: 5,
        title: "Worked examples",
        review_answered: 0,
        review_total: 1,
        done: false,
      },
    ],
  };
}

function readPayload() {
  return {
    lesson_id: "ASC842-GDE-04",
    title: "Verifying the output",
    kind: "text",
    word_count: 40,
    course_title: "Identifying a Lease Under ASC 842",
    lesson_position: 4,
    lesson_count: 6,
    section_count: 7,
    sections_completed: 2,
    sections: [
      {
        section_key: "sec-00",
        role: "front_matter",
        title: "How this course works",
        position: 0,
        locked: false,
        markdown: "## How this course works\n\nRead it in order.",
        question_keys: [],
      },
      {
        section_key: "sec-01",
        role: "body",
        title: "Checking the total",
        position: 1,
        locked: false,
        markdown: "# Checking the total\n\nAdd the column.",
        question_keys: [],
      },
    ],
    media: [],
    questions: [],
  };
}

function playPayload() {
  return {
    lesson_id: "ASC842-GDE-05",
    title: "Worked examples",
    video_url: "https://media.example/ex.mp4",
    duration_seconds: 120,
    blocks: [],
    questions: [],
    furthest_seconds: 0,
  };
}

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.getMyEnrollment.mockResolvedValue(enrollment());
  api.getMyReadLesson.mockResolvedValue(readPayload());
  api.getMyPlayLesson.mockResolvedValue(playPayload());
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

async function render(packageId) {
  const path = `/my/courses/12/lessons/${packageId}`;
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/my/courses/:enrollmentId/lessons/:packageId"
            element={<MyLesson />}
          />
        </Routes>
      </MemoryRouter>
    );
  });
  await flush();
}

const crumb = () => container.querySelector("p").textContent;

describe("MyLesson breadcrumb (037)", () => {
  it("names the course and the lesson for a text lesson", async () => {
    await render(READ_PACKAGE_ID);
    expect(crumb()).toBe(
      "My courses / Identifying a Lease Under ASC 842 / " +
        "Lesson 4: Verifying the output"
    );
  });

  it("carries no placeholder text", async () => {
    await render(READ_PACKAGE_ID);
    expect(crumb()).not.toMatch(/\/ course \//);
    expect(crumb()).not.toMatch(/\/ lesson$/);
  });

  it("links the course crumb to the course page", async () => {
    await render(READ_PACKAGE_ID);
    const links = Array.from(container.querySelectorAll("p a"));
    expect(links.map((a) => a.textContent)).toEqual([
      "My courses",
      "Identifying a Lease Under ASC 842",
    ]);
    expect(links[1].getAttribute("href")).toBe("/my/courses/12");
  });

  it("names a video lesson too, from the enrollment detail", async () => {
    await render(PLAY_PACKAGE_ID);
    expect(crumb()).toBe(
      "My courses / Identifying a Lease Under ASC 842 / " +
        "Lesson 5: Worked examples"
    );
  });

  it("shows only what has loaded, never a name guessed from the URL", async () => {
    api.getMyEnrollment.mockRejectedValue(new Error("down"));
    await render(READ_PACKAGE_ID);
    expect(crumb()).toBe("My courses");
  });
});
