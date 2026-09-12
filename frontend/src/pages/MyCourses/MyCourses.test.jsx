/**
 * 028: an expired card renews at no charge only when the payload says
 * `renewable`; clicking calls /renew and opens the new enrollment.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MyCourses from "./MyCourses.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  listMyCourses: vi.fn(),
  renewCourse: vi.fn(),
}));

vi.mock("../../api/my", async (importOriginal) => ({
  ...(await importOriginal()),
  listMyCourses: api.listMyCourses,
}));

vi.mock("../../api/courses", async (importOriginal) => ({
  ...(await importOriginal()),
  renewCourse: api.renewCourse,
}));

function card(overrides = {}) {
  return {
    enrollment_id: 5,
    course_code: "ATO",
    title: "Account Takeover",
    status: "expired",
    enrolled_at: "2025-09-01T00:00:00Z",
    expires_at: "2026-09-01T00:00:00Z",
    credit: "1.0",
    field_of_study: "Information Technology",
    lessons_total: 2,
    lessons_done: 1,
    lessons_kind: "text",
    review_answered: 2,
    review_total: 4,
    assessment_available: false,
    retakes_remaining: null,
    retakes_unlimited: true,
    failed_attempts: 0,
    open_attempt_id: null,
    completion: null,
    renewable: false,
    ...overrides,
  };
}

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

function button(text) {
  return Array.from(document.querySelectorAll("button")).find((b) =>
    b.textContent.startsWith(text)
  );
}

describe("MyCourses renewal (028)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.listMyCourses.mockReset();
    api.renewCourse.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(cards) {
    api.listMyCourses.mockResolvedValue(cards);
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/my/courses"]}>
          <Routes>
            <Route path="/my/courses" element={<MyCourses />} />
            <Route path="/my/courses/:enrollmentId" element={<p>opened enrollment</p>} />
          </Routes>
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("shows Expired, not a button, when the payload is not renewable", async () => {
    await mount([card()]);
    expect(container.textContent).toContain("Expired");
    expect(button("Start a new enrollment")).toBeUndefined();
  });

  it("shows the renewal button when renewable, calls /renew, and opens the new enrollment", async () => {
    await mount([card({ renewable: true })]);
    const renew = button("Start a new enrollment (no charge)");
    expect(renew).toBeDefined();
    expect(container.textContent).toContain("costs nothing");
    api.renewCourse.mockResolvedValue(card({ enrollment_id: 9, status: "active", renewable: false }));
    act(() => {
      renew.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(api.renewCourse).toHaveBeenCalledWith("ATO");
    expect(container.textContent).toContain("opened enrollment");
  });

  it("re-take labels carry no count under the unlimited policy", async () => {
    await mount([
      card({ status: "active", assessment_available: true, failed_attempts: 3 }),
    ]);
    expect(container.textContent).toContain("Re-take the qualified assessment");
    expect(container.textContent).not.toContain("left)");
  });
});
