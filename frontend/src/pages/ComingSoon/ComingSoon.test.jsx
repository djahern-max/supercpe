/**
 * 024: while coming_soon the only public page says the name and "Coming
 * Soon" and makes no program claim — no self-study, no CPE credit, no
 * course, no Registry (8.01: partial disclosure is worse than none).
 * 033: the name is the brand logo image; the page fetches nothing from
 * another origin; the waiting-list form still submits.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComingSoon from "./ComingSoon.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  joinWaitingList: vi.fn(() => Promise.resolve({ message: "ignored" })),
}));

vi.mock("../../api/landing", () => ({
  joinWaitingList: api.joinWaitingList,
}));

function setValue(element, value) {
  const setter = Object.getOwnPropertyDescriptor(
    element.tagName === "SELECT"
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype,
    "value",
  ).set;
  setter.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

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

  it("renders the brand logo as the heading and Coming Soon", () => {
    const logo = container.querySelector("h1 img");
    expect(logo.getAttribute("alt")).toBe("superCPE");
    expect(logo.getAttribute("src")).toMatch(/logo\.png$/);
    expect(container.textContent).toContain("Coming Soon");
  });

  it("fetches nothing from another origin", () => {
    for (const element of container.querySelectorAll("[src], [href]")) {
      const url = element.getAttribute("src") || element.getAttribute("href");
      expect(url).not.toMatch(/^(https?:)?\/\//);
    }
    expect(container.querySelector("script, link, iframe")).toBeNull();
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
    expect(container.querySelector("a")).toBeNull();
  });

  it("submits the waiting-list form and shows the joined line", async () => {
    api.joinWaitingList.mockClear();
    const [name, email] = container.querySelectorAll("input:not([tabindex])");
    const state = container.querySelector("select");
    await act(async () => {
      setValue(name, "Pat Example");
      setValue(email, "pat@example.test");
      setValue(state, "NH");
    });
    const submit = container.querySelector("button[type=submit]");
    expect(submit.disabled).toBe(false);
    await act(async () => {
      container.querySelector("form").dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    expect(api.joinWaitingList).toHaveBeenCalledTimes(1);
    expect(api.joinWaitingList.mock.calls[0][0]).toMatchObject({
      name: "Pat Example",
      email: "pat@example.test",
      state: "NH",
      website: "",
    });
    expect(container.textContent).toContain("You're on the list.");
    expect(container.querySelector("form")).toBeNull();
  });
});
