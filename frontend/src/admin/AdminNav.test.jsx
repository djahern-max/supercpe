/**
 * 033: the admin chrome on a phone. Below 720px the links hide behind a
 * menu button until it is pressed; Sign out is present in both states
 * and signs out once. Above 720px every link is in the row and there is
 * no button. The width comes from matchMedia, stubbed here.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminNav from "./AdminNav.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const session = vi.hoisted(() => ({
  account: { id: 1, email: "admin@supercpe.test", role: "admin" },
  signOut: vi.fn(() => Promise.resolve()),
}));

vi.mock("../auth/SessionContext.jsx", () => ({
  useSession: () => session,
}));

const LABELS = [
  "Courses",
  "Packages",
  "Payments",
  "Subscriptions",
  "Experts",
  "Sponsor",
  "Accounts",
  "Jurisdictions",
  "Waiting list",
];

function stubViewport(narrow) {
  vi.stubGlobal("matchMedia", (query) => ({
    matches: narrow && query === "(max-width: 720px)",
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

const visibleLinks = (container) =>
  [...container.querySelectorAll("a[href^='/admin/']")]
    .filter((a) => !a.closest("[hidden]"))
    .map((a) => a.textContent)
    .filter((text) => text !== "Admin");

const buttons = (container, label) =>
  [...container.querySelectorAll("button")].filter((b) => b.textContent === label);

async function click(element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("AdminNav", () => {
  let container;
  let root;

  async function mount() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/admin/courses"]}>
          <AdminNav />
        </MemoryRouter>
      );
    });
  }

  beforeEach(() => {
    session.signOut.mockClear();
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("narrow: links hidden until the menu button is pressed; the email with them", async () => {
    stubViewport(true);
    await mount();
    const [menu] = buttons(container, "Menu");
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    expect(visibleLinks(container)).toEqual([]);
    const panel = container.querySelector(`#${menu.getAttribute("aria-controls")}`);
    expect(panel.hidden).toBe(true);
    // The email is only inside the hidden panel, nowhere in the row.
    expect(container.querySelector(".row, [class*='row']").textContent).not.toContain(
      "admin@supercpe.test"
    );

    await click(menu);
    expect(menu.getAttribute("aria-expanded")).toBe("true");
    expect(panel.hidden).toBe(false);
    expect(visibleLinks(container)).toEqual(LABELS);
    expect(panel.textContent).toContain("admin@supercpe.test");

    await click(menu);
    expect(visibleLinks(container)).toEqual([]);
  });

  it("narrow: Sign out is present closed and open, and signs out once", async () => {
    stubViewport(true);
    await mount();
    expect(buttons(container, "Sign out")).toHaveLength(1);
    await click(buttons(container, "Menu")[0]);
    const [signOut] = buttons(container, "Sign out");
    expect(buttons(container, "Sign out")).toHaveLength(1);
    await click(signOut);
    expect(session.signOut).toHaveBeenCalledTimes(1);
  });

  it("wide: every link in the row, the email, Sign out, and no menu button", async () => {
    stubViewport(false);
    await mount();
    expect(buttons(container, "Menu")).toHaveLength(0);
    expect(visibleLinks(container)).toEqual(LABELS);
    expect(container.textContent).toContain("admin@supercpe.test");
    expect(buttons(container, "Sign out")).toHaveLength(1);
  });

  it("without matchMedia (an old browser) it renders the wide row", async () => {
    await mount();
    expect(buttons(container, "Menu")).toHaveLength(0);
    expect(visibleLinks(container)).toEqual(LABELS);
  });

  it("carries the mark with empty alt text and no course fact", async () => {
    stubViewport(false);
    await mount();
    const mark = container.querySelector("img");
    expect(mark.getAttribute("alt")).toBe("");
    expect(mark.getAttribute("src")).toMatch(/mark\.png$/);
    for (const word of ["National Registry", "credit", "$"]) {
      expect(container.textContent).not.toContain(word);
    }
  });
});
