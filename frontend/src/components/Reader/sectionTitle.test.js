import { describe, expect, it } from "vitest";
import { stripLeadingTitle } from "./sectionTitle.js";

describe("stripLeadingTitle (023c F3)", () => {
  it("drops a leading heading that repeats the section title", () => {
    const markdown = "# Identifying a Lease\n\nA contract is a lease when…";
    expect(stripLeadingTitle(markdown, "Identifying a Lease")).toBe(
      "\nA contract is a lease when…"
    );
  });

  it("matches case, spacing, and emphasis loosely, any heading level", () => {
    expect(
      stripLeadingTitle("\n\n##  **identifying**   a lease  \nBody", "Identifying a Lease")
    ).toBe("Body");
  });

  it("keeps a heading that says something else", () => {
    const markdown = "# Overview\n\nBody";
    expect(stripLeadingTitle(markdown, "Identifying a Lease")).toBe(markdown);
  });

  it("keeps a heading that is not the first thing in the section", () => {
    const markdown = "Preamble\n\n# Identifying a Lease\n\nBody";
    expect(stripLeadingTitle(markdown, "Identifying a Lease")).toBe(markdown);
  });

  it("leaves null (a locked section) and empty text alone", () => {
    expect(stripLeadingTitle(null, "T")).toBe(null);
    expect(stripLeadingTitle("", "T")).toBe("");
  });
});
