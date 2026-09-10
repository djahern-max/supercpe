import { describe, expect, it } from "vitest";
import { retryAdvice } from "./retryAdvice.js";

describe("retryAdvice (023c F1)", () => {
  it("tells a study-guide participant to re-read", () => {
    expect(retryAdvice("text")).toBe(
      "Consider re-reading the guide before trying again."
    );
    expect(retryAdvice("text")).not.toContain("watch");
  });
  it("keeps the video wording for a video course", () => {
    expect(retryAdvice("video")).toBe(
      "Consider re-watching the lessons before trying again."
    );
  });
  it("names both for a mixed or unknown course", () => {
    expect(retryAdvice("mixed")).toContain("re-reading the guide");
    expect(retryAdvice("mixed")).toContain("re-watching the lessons");
    expect(retryAdvice(undefined)).toBe(retryAdvice("mixed"));
  });
});
