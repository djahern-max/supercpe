/**
 * 030: rendered through the real App so the gate, the routes, and the
 * button are exercised together — the coming-soon landing page and the
 * admin pages never ask for the Google config and never inject the GIS
 * script; the sign-in page at open does.
 *
 * 030a reverses one 030 assertion: the coming-soon sign-in page now asks
 * for the config, because the server decides what a closed site answers
 * (the gate's 404 unless the operator listed preview addresses). The
 * property that survives is "never loads GIS unless the config answers".
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App.jsx";
import { ApiError } from "../../api/client";
import { GIS_SCRIPT_SRC } from "../../auth/googleIdentity";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getSite: vi.fn(),
  getMe: vi.fn(),
  logout: vi.fn(),
  getGoogleConfig: vi.fn(),
}));
const gis = vi.hoisted(() => ({ load: vi.fn() }));

vi.mock("../../api/site", async (importOriginal) => ({
  ...(await importOriginal()),
  getSite: api.getSite,
}));
vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal()),
  getMe: api.getMe,
  logout: api.logout,
  getGoogleConfig: api.getGoogleConfig,
}));
vi.mock("../../auth/googleIdentity", async (importOriginal) => ({
  ...(await importOriginal()),
  loadGoogleIdentity: gis.load,
}));

const ADMIN = {
  id: 1,
  email: "admin@example.com",
  role: "admin",
  must_change_password: false,
  signin_methods: ["password"],
};

const gisScripts = () =>
  document.head.querySelectorAll(`script[src="${GIS_SCRIPT_SRC}"]`);

describe("GIS script placement (030)", () => {
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
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    api.getSite.mockReset();
    api.getMe.mockReset();
    api.logout.mockReset().mockResolvedValue(undefined);
    api.getGoogleConfig.mockReset().mockResolvedValue({ client_id: "cid.apps" });
    gis.load.mockReset().mockResolvedValue({
      initialize: vi.fn(),
      renderButton: vi.fn(),
    });
    // Every other page read fails; nothing here depends on one.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("the coming-soon landing page asks nothing of Google", async () => {
    api.getSite.mockResolvedValue({ site_mode: "coming_soon", sponsor_name: "S" });
    api.getMe.mockRejectedValue(new Error("401"));
    await mount("/");
    expect(api.getGoogleConfig).not.toHaveBeenCalled();
    expect(gis.load).not.toHaveBeenCalled();
    expect(gisScripts()).toHaveLength(0);
  });

  it("the sign-in page while coming-soon asks for the config; on the gate's 404 nothing loads (030a)", async () => {
    api.getSite.mockResolvedValue({ site_mode: "coming_soon", sponsor_name: "S" });
    api.getMe.mockRejectedValue(new Error("401"));
    api.getGoogleConfig.mockRejectedValue(
      new ApiError(404, { detail: "Not found" })
    );
    await mount("/login");
    expect(api.getGoogleConfig).toHaveBeenCalledTimes(1);
    expect(gis.load).not.toHaveBeenCalled();
    expect(gisScripts()).toHaveLength(0);
    expect(
      Array.from(container.querySelectorAll("span")).some(
        (span) => span.textContent === "or"
      )
    ).toBe(false);
  });

  it("the sign-in page while coming-soon loads GIS once when the config answers (030a)", async () => {
    api.getSite.mockResolvedValue({ site_mode: "coming_soon", sponsor_name: "S" });
    api.getMe.mockRejectedValue(new Error("401"));
    await mount("/login");
    expect(api.getGoogleConfig).toHaveBeenCalledTimes(1);
    expect(gis.load).toHaveBeenCalledTimes(1);
  });

  it("an admin page asks nothing of Google, even at open", async () => {
    api.getSite.mockResolvedValue({ site_mode: "open", sponsor_name: "S" });
    api.getMe.mockResolvedValue(ADMIN);
    await mount("/admin/courses");
    expect(api.getGoogleConfig).not.toHaveBeenCalled();
    expect(gis.load).not.toHaveBeenCalled();
    expect(gisScripts()).toHaveLength(0);
  });

  it("the sign-in page at open loads GIS exactly once", async () => {
    api.getSite.mockResolvedValue({ site_mode: "open", sponsor_name: "S" });
    api.getMe.mockRejectedValue(new Error("401"));
    await mount("/login");
    expect(api.getGoogleConfig).toHaveBeenCalledTimes(1);
    expect(gis.load).toHaveBeenCalledTimes(1);
  });
});
