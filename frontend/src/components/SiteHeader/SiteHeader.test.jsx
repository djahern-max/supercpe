/**
 * 025: the site header renders above every open surface and nowhere
 * near the coming-soon page (8.01: no "Courses" link over a page that
 * 024 stripped to a wordmark), nor under /admin, nor on /change-password.
 * Rendered through the real App so the gate, the header, and the routes
 * are exercised together.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getSite: vi.fn(),
  getMe: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("../../api/site", async (importOriginal) => ({
  ...(await importOriginal()),
  getSite: api.getSite,
}));
vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal()),
  getMe: api.getMe,
  logout: api.logout,
}));

const PARTICIPANT = {
  id: 1,
  email: "cpa@example.com",
  role: "participant",
  must_change_password: false,
};

function siteMode(mode) {
  api.getSite.mockResolvedValue({ site_mode: mode, sponsor_name: "Sponsor" });
}

function signedIn(account) {
  api.getMe.mockResolvedValue(account);
}

function signedOut() {
  api.getMe.mockRejectedValue(new Error("401"));
}

const siteNav = (container) => container.querySelector('nav[aria-label="Site"]');
const linkTexts = (nav) => [...nav.querySelectorAll("a")].map((a) => a.textContent);

async function click(element) {
  await act(async () => {
    element.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })
    );
  });
}

describe("SiteHeader", () => {
  let container;
  let root;

  async function mount(path) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      );
    });
  }

  beforeEach(() => {
    api.getSite.mockReset();
    api.getMe.mockReset();
    api.logout.mockReset().mockResolvedValue(undefined);
    // Every page fetches its own data; none of it matters here.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  });

  afterEach(async () => {
    if (root) {
      await act(async () => {
        root.unmount();
      });
      root = null;
    }
    container?.remove();
    vi.unstubAllGlobals();
  });

  it("signed out at open: four links, wordmark to /, Sign in reaches login", async () => {
    siteMode("open");
    signedOut();
    await mount("/");
    const nav = siteNav(container);
    expect(linkTexts(nav)).toEqual([
      "Courses",
      "How it works",
      "Sign in",
      "Create account",
    ]);
    expect(nav.querySelector("button")).toBeNull();
    const wordmark = container.querySelector("header a");
    expect(wordmark.textContent).toBe("superCPE");
    expect(wordmark.getAttribute("href")).toBe("/");

    await click(nav.querySelector('a[href="/login"]'));
    expect(container.querySelector("#login-email")).not.toBeNull();
    // The header stays on /login.
    expect(siteNav(container)).not.toBeNull();
  });

  it("signed out in coming_soon: no header markup on any public path", async () => {
    for (const path of ["/", "/courses", "/courses/ATO", "/no-such-page"]) {
      siteMode("coming_soon");
      signedOut();
      await mount(path);
      expect(container.querySelector("header")).toBeNull();
      expect(container.querySelector("nav")).toBeNull();
      expect(container.textContent).toContain("Coming Soon");
      expect(container.textContent).not.toContain("National Registry");
      await act(async () => {
        root.unmount();
      });
      root = null;
      container.remove();
    }
  });

  it("participant in coming_soon: header renders; Sign out lands on the coming-soon page", async () => {
    siteMode("coming_soon");
    signedIn(PARTICIPANT);
    await mount("/my/courses");
    const nav = siteNav(container);
    expect(linkTexts(nav)).toEqual(["My courses", "Courses", "Account"]);
    expect(nav.textContent).toContain(PARTICIPANT.email);
    expect(container.querySelector("header a").getAttribute("href")).toBe(
      "/my/courses"
    );

    const signOut = [...nav.querySelectorAll("button")].find(
      (b) => b.textContent === "Sign out"
    );
    await click(signOut);
    expect(api.logout).toHaveBeenCalledTimes(1);
    expect(siteNav(container)).toBeNull();
    expect(container.querySelector("header")).toBeNull();
    expect(container.textContent).toContain("Coming Soon");
  });

  it("admin under /admin: no site header, one Sign out", async () => {
    siteMode("open");
    signedIn({ ...PARTICIPANT, role: "admin" });
    await mount("/admin/courses");
    expect(siteNav(container)).toBeNull();
    const signOuts = [...container.querySelectorAll("button")].filter(
      (b) => b.textContent === "Sign out"
    );
    expect(signOuts).toHaveLength(1);
  });

  it("reviewer: header with Review and Sign out on both review pages", async () => {
    for (const path of ["/review", "/review/courses/ATO"]) {
      siteMode("open");
      signedIn({ ...PARTICIPANT, role: "reviewer" });
      await mount(path);
      const nav = siteNav(container);
      expect(linkTexts(nav)).toEqual(["Review"]);
      expect(nav.querySelector("button").textContent).toBe("Sign out");
      expect(container.querySelector("header a").getAttribute("href")).toBe(
        "/review"
      );
      await act(async () => {
        root.unmount();
      });
      root = null;
      container.remove();
    }
  });

  it("forced password change: no header on /change-password", async () => {
    siteMode("open");
    signedIn({ ...PARTICIPANT, must_change_password: true });
    await mount("/change-password");
    expect(siteNav(container)).toBeNull();
  });

  it("states no course fact and nothing about the Registry", async () => {
    siteMode("open");
    signedIn(PARTICIPANT);
    await mount("/policies");
    const text = container.querySelector("header").textContent;
    for (const word of ["National Registry", "credit", "$", "Sponsor", "ATO"]) {
      expect(text).not.toContain(word);
    }
  });
});
