/**
 * 027: the chrome after the walkthrough — one Sign out (the 025 header's)
 * on /my/courses and /review, a Create account link on /login at open and
 * never in coming-soon signed out, and a footer under the header's own
 * rule: absent in coming-soon signed out, absent under /admin, present at
 * open, and saying nothing about a course or the Registry. Rendered
 * through the real App so the gate, the header, the footer, and the
 * routes are exercised together, as the 025 test does.
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

/** Every page fetches its own data; only the sponsor read answers. */
function stubFetch(sponsor) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => {
      if (sponsor && String(url).endsWith("/api/v1/sponsor")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: { get: () => "application/json" },
          json: () => Promise.resolve(sponsor),
        });
      }
      return Promise.reject(new Error("offline"));
    })
  );
}

const footer = (container) => container.querySelector("footer");
const footerNav = (container) =>
  container.querySelector('nav[aria-label="Site footer"]');
const signOuts = (container) =>
  [...container.querySelectorAll("button")].filter(
    (b) => b.textContent === "Sign out"
  );

describe("Chrome after 027", () => {
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
    // Let the footer's sponsor read settle.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  async function unmount() {
    if (root) {
      await act(async () => {
        root.unmount();
      });
      root = null;
    }
    container?.remove();
  }

  beforeEach(() => {
    api.getSite.mockReset();
    api.getMe.mockReset();
    api.logout.mockReset().mockResolvedValue(undefined);
    stubFetch(null);
  });

  afterEach(async () => {
    await unmount();
    vi.unstubAllGlobals();
  });

  it("footer at open: policies, how it works, and the contact address", async () => {
    siteMode("open");
    signedOut();
    stubFetch({ name: "Sponsor", website: "", contact_email: "help@example.com" });
    await mount("/policies");
    const nav = footerNav(container);
    expect(nav.querySelector('a[href="/policies"]').textContent).toBe("Policies");
    expect(nav.querySelector('a[href="/how-it-works"]').textContent).toBe(
      "How it works"
    );
    expect(nav.querySelector('a[href="mailto:help@example.com"]').textContent).toBe(
      "help@example.com"
    );
    // One header, one footer.
    expect(container.querySelectorAll("header")).toHaveLength(1);
    expect(container.querySelectorAll("footer")).toHaveLength(1);
  });

  it("footer without the sponsor read: the two links, no address", async () => {
    siteMode("open");
    signedOut();
    await mount("/");
    const nav = footerNav(container);
    expect([...nav.querySelectorAll("a")].map((a) => a.textContent)).toEqual([
      "Policies",
      "How it works",
    ]);
  });

  it("states no course fact and nothing about the Registry", async () => {
    siteMode("open");
    signedIn(PARTICIPANT);
    stubFetch({ name: "Sponsor", website: "", contact_email: "help@example.com" });
    await mount("/policies");
    const text = footer(container).textContent;
    for (const word of ["National Registry", "credit", "$", "Sponsor", "ATO"]) {
      expect(text).not.toContain(word);
    }
  });

  it("no footer in coming_soon signed out, on any public path", async () => {
    for (const path of ["/", "/courses", "/policies", "/login"]) {
      siteMode("coming_soon");
      signedOut();
      await mount(path);
      expect(footer(container)).toBeNull();
      expect(container.querySelector("nav")).toBeNull();
      await unmount();
    }
  });

  it("no footer under /admin", async () => {
    siteMode("open");
    signedIn({ ...PARTICIPANT, role: "admin" });
    await mount("/admin/courses");
    expect(footer(container)).toBeNull();
    expect(signOuts(container)).toHaveLength(1);
  });

  it("no footer on /change-password", async () => {
    siteMode("open");
    signedIn({ ...PARTICIPANT, must_change_password: true });
    await mount("/change-password");
    expect(footer(container)).toBeNull();
  });

  it("/login shows Create account at open and not in coming-soon signed out", async () => {
    siteMode("open");
    signedOut();
    await mount("/login");
    const link = container.querySelector('main a[href="/register"]');
    expect(link.textContent).toBe("Create account");
    await unmount();

    siteMode("coming_soon");
    signedOut();
    await mount("/login");
    expect(container.querySelector("#login-email")).not.toBeNull();
    expect(container.querySelector('a[href="/register"]')).toBeNull();
    expect(container.querySelector("header")).toBeNull();
    expect(container.querySelector("footer")).toBeNull();
  });

  it("one Sign out on /my/courses and on the review pages", async () => {
    siteMode("open");
    signedIn(PARTICIPANT);
    await mount("/my/courses");
    expect(signOuts(container)).toHaveLength(1);
    expect(container.querySelectorAll("header")).toHaveLength(1);
    // The email appears once: in the header, not on the page.
    expect(container.textContent.split(PARTICIPANT.email)).toHaveLength(2);
    await unmount();

    for (const path of ["/review", "/review/courses/ATO"]) {
      siteMode("open");
      signedIn({ ...PARTICIPANT, role: "reviewer" });
      await mount(path);
      expect(signOuts(container)).toHaveLength(1);
      expect(container.querySelectorAll("header")).toHaveLength(1);
      expect(container.textContent.split(PARTICIPANT.email)).toHaveLength(2);
      await unmount();
    }
  });
});
