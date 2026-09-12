/**
 * 028: the Registration section offers "Start a new enrollment (no
 * charge)" for an expired, renewable enrollment instead of the price;
 * on success it re-renders enrolled without leaving the page.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CoursePage from "./CoursePage.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getPublicCourse: vi.fn(),
  getJurisdictionNote: vi.fn(),
  renewCourse: vi.fn(),
  listMyCourses: vi.fn(),
  startCheckout: vi.fn(),
}));

vi.mock("../../api/courses", () => ({
  getPublicCourse: api.getPublicCourse,
  getJurisdictionNote: api.getJurisdictionNote,
  renewCourse: api.renewCourse,
}));
vi.mock("../../api/my", async (importOriginal) => ({
  ...(await importOriginal()),
  listMyCourses: api.listMyCourses,
}));
vi.mock("../../api/checkout", () => ({ startCheckout: api.startCheckout }));
vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: { id: 3, email: "pat@supercpe.test", role: "participant" },
    loading: false,
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

const COURSE = {
  program_type: "QAS Self Study",
  developed_by: null,
  reviewed_by: null,
  last_reviewed: null,
  last_documented_date: null,
  recommended_credit: "1.0",
  credit_basis: "",
  course_code: "ATO",
  title: "Account Takeover",
  description: "A course.",
  field_of_study: "Information Technology",
  knowledge_level: "Basic",
  prerequisites: "None",
  advance_preparation: "None",
  lesson_count: 1,
  total_duration_seconds: 0,
  total_section_count: 3,
  price_cents: 4900,
  registration_policy: null,
  refund_policy: null,
  complaint_policy: null,
  sponsor_statement: null,
  objectives: [],
  lessons: [],
  outline: [],
};

function enrollment(overrides = {}) {
  return {
    enrollment_id: 5,
    course_code: "ATO",
    status: "expired",
    expires_at: "2026-09-01T00:00:00Z",
    renewable: false,
    ...overrides,
  };
}

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

function button(text) {
  return Array.from(document.querySelectorAll("button")).find((b) =>
    b.textContent.startsWith(text)
  );
}

describe("CoursePage registration renewal (028)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.getPublicCourse.mockResolvedValue(COURSE);
    api.getJurisdictionNote.mockRejectedValue(new Error("404"));
    api.renewCourse.mockReset();
    api.startCheckout.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(mine) {
    api.listMyCourses.mockResolvedValue(mine);
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/courses/ATO"]}>
          <Routes>
            <Route path="/courses/:code" element={<CoursePage />} />
          </Routes>
        </MemoryRouter>
      );
    });
    await flush();
    await flush();
  }

  it("an expired enrollment without eligibility shows the price and Enroll", async () => {
    await mount([enrollment()]);
    expect(button("Enroll")).toBeDefined();
    expect(container.textContent).toContain("$49.00");
    expect(button("Start a new enrollment")).toBeUndefined();
  });

  it("an expired renewable enrollment shows the renewal button and re-renders enrolled on success", async () => {
    await mount([enrollment({ renewable: true })]);
    const renew = button("Start a new enrollment (no charge)");
    expect(renew).toBeDefined();
    expect(button("Enroll")).toBeUndefined();
    expect(container.textContent).not.toContain("$49.00");
    expect(container.textContent).toContain("expired on");

    api.renewCourse.mockResolvedValue(
      enrollment({ enrollment_id: 9, status: "active", renewable: false })
    );
    act(() => {
      renew.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(api.renewCourse).toHaveBeenCalledWith("ATO");
    expect(api.startCheckout).not.toHaveBeenCalled();
    expect(container.textContent).toContain("You're enrolled in this course.");
    expect(container.querySelector('a[href="/my/courses/9"]').textContent).toBe(
      "Continue the course."
    );
  });

  it("shows the server's refusal lines when /renew answers 422", async () => {
    const { ApiError } = await import("../../api/client");
    await mount([enrollment({ renewable: true })]);
    api.renewCourse.mockRejectedValue(
      new ApiError(422, { errors: ["your enrollment on ATO is still active, expiring 2027-01-01"] })
    );
    act(() => {
      button("Start a new enrollment").dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    await flush();
    expect(container.textContent).toContain("still active");
  });
});
