/**
 * 024: while coming_soon the only public page says the name and "Coming
 * Soon" and makes no program claim — no self-study, no CPE credit, no
 * course, no Registry (8.01: partial disclosure is worse than none).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComingSoon from "./ComingSoon.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../api/landing", () => ({
  joinWaitingList: vi.fn(() => Promise.resolve({ message: "ignored" })),
}));

describe("ComingSoon", () => {
  let container;
  let root;

  beforeEach(async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(<ComingSoon />);
    });
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("renders the wordmark and Coming Soon", () => {
    const h1 = container.querySelector("h1");
    expect(h1.textContent).toBe("superCPE");
    expect(container.textContent).toContain("Coming Soon");
  });

  it("makes no program claim", () => {
    const text = container.textContent;
    for (const claim of [
      "National Registry",
      "842",
      "CPE credit",
      "Self-study",
      "self-study",
      "Self study",
      "licensed CPA",
      "course",
    ]) {
      expect(text).not.toContain(claim);
    }
  });

  it("keeps the waiting-list form neutral", () => {
    expect(container.textContent).toContain("Email");
    expect(container.querySelector("button[type=submit]").textContent).toBe(
      "Notify me",
    );
    expect(container.querySelector("a[href='/login']")).toBeNull();
  });
});
