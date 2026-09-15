/**
 * 035: the catalog card. The two things worth pinning are that the card
 * renders the artwork when the payload carries a URL, and that it
 * degrades to text — keeping its shape, growing no placeholder — when
 * the URL is null, which is what most courses look like on day one.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Catalog from "./Catalog.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ listPublicCourses: vi.fn() }));

vi.mock("../../api/courses", () => ({
  listPublicCourses: api.listPublicCourses,
}));

const COURSE = {
  course_code: "GPT",
  title: "Generative AI for the CPA",
  description: "What a language model can and cannot be trusted with.",
  program_type: "Self study",
  field_of_study: "Information Technology",
  knowledge_level: "Basic",
  prerequisites: "None",
  advance_preparation: "None",
  lesson_count: 6,
  total_duration_seconds: 420,
  total_section_count: 39,
  price_cents: 2900,
  thumbnail_url: "/api/v1/courses/GPT/thumbnail?v=abc123def456",
  recommended_credit: "3.2",
  credit_basis: "word count formula",
  developed_by: null,
  reviewed_by: null,
  last_reviewed: null,
  last_documented_date: null,
};

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

describe("Catalog card (035)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.listPublicCourses.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(courses) {
    api.listPublicCourses.mockResolvedValue(courses);
    act(() => {
      root.render(
        <MemoryRouter>
          <Catalog />
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("renders the artwork and the credit figure", async () => {
    await mount([COURSE]);

    const image = container.querySelector("img");
    expect(image).not.toBeNull();
    expect(image.getAttribute("src")).toContain(
      "/api/v1/courses/GPT/thumbnail?v=abc123def456"
    );
    // The title beside it is the accessible name; the picture is not
    // described a second time.
    expect(image.getAttribute("alt")).toBe("");
    expect(container.textContent).toContain("3.2 credits");
    expect(container.textContent).toContain("$29.00");
    expect(container.textContent).toContain(
      "Information Technology · Basic · 6 lessons · study guide · 39 sections · 7 minutes of video"
    );
  });

  it("degrades to text with no artwork and no placeholder", async () => {
    await mount([{ ...COURSE, thumbnail_url: null }]);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a[href='/courses/GPT']")).not.toBeNull();
    expect(container.textContent).toContain("Generative AI for the CPA");
    expect(container.textContent).toContain("3.2 credits");
  });

  it("says one credit in the singular", async () => {
    await mount([{ ...COURSE, recommended_credit: "1.0" }]);
    expect(container.textContent).toContain("1.0 credit");
    expect(container.textContent).not.toContain("1.0 credits");
  });

  it("shows the empty state when nothing is published", async () => {
    await mount([]);
    expect(container.textContent).toContain("No courses are published yet.");
    expect(container.querySelector("ul")).toBeNull();
  });
});
