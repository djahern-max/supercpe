/**
 * 030: the sign-in page renders Google's button only at open and only
 * when the config carries a client id; the GIS global is mocked. A
 * successful callback POSTs the credential and routes exactly as
 * password login does; the constant 401 shows one generic line.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { GOOGLE_SIGN_IN_FAILED } from "../../components/GoogleSignIn/GoogleSignIn.jsx";
import Login from "./Login.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  login: vi.fn(),
  getGoogleConfig: vi.fn(),
  loginWithGoogle: vi.fn(),
}));
const gis = vi.hoisted(() => ({
  load: vi.fn(),
  initialize: vi.fn(),
  renderButton: vi.fn(),
}));
const site = vi.hoisted(() => ({ face: "open" }));
const session = vi.hoisted(() => ({ setAccount: vi.fn() }));

vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal()),
  login: api.login,
  getGoogleConfig: api.getGoogleConfig,
  loginWithGoogle: api.loginWithGoogle,
}));
vi.mock("../../auth/googleIdentity", () => ({
  GIS_SCRIPT_SRC: "https://accounts.google.com/gsi/client",
  loadGoogleIdentity: gis.load,
}));
vi.mock("../../site/SiteContext.jsx", async (importOriginal) => {
  const original = await importOriginal();
  return { ...original, useSiteFace: () => site.face };
});
vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: null,
    loading: false,
    refresh: vi.fn(),
    setAccount: session.setAccount,
    signOut: vi.fn(),
  }),
}));

const PARTICIPANT = {
  id: 7,
  email: "pat@example.test",
  role: "participant",
  display_name: "Pat",
  must_change_password: false,
  subscription_current: false,
  signin_methods: ["google"],
};

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

const gisCallback = () => gis.initialize.mock.calls[0][0].callback;

describe("Login page: Google sign-in (030)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.login.mockReset();
    api.getGoogleConfig.mockReset();
    api.loginWithGoogle.mockReset();
    gis.load.mockReset().mockResolvedValue({
      initialize: gis.initialize,
      renderButton: gis.renderButton,
    });
    gis.initialize.mockReset();
    gis.renderButton.mockReset();
    session.setAccount.mockReset();
    site.face = "open";
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(state) {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={[{ pathname: "/login", state }]}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/my/courses" element={<p>My courses page</p>} />
            <Route path="/change-password" element={<p>Change password page</p>} />
            <Route path="/courses/ATO" element={<p>Course page</p>} />
          </Routes>
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("renders the button at open with a client id: popup, no auto-select", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    await mount();
    expect(gis.load).toHaveBeenCalledTimes(1);
    expect(gis.initialize).toHaveBeenCalledTimes(1);
    const config = gis.initialize.mock.calls[0][0];
    expect(config.client_id).toBe("cid.apps");
    expect(config.ux_mode).toBe("popup");
    expect(config.auto_select).toBe(false);
    expect(gis.renderButton).toHaveBeenCalledTimes(1);
    expect(gis.renderButton.mock.calls[0][0]).toBeInstanceOf(HTMLElement);
    expect(gis.renderButton.mock.calls[0][1].text).toBe("signin_with");
    expect(container.textContent).toContain("or");
    // The password form is untouched.
    expect(container.querySelector("#login-password")).not.toBeNull();
  });

  it("renders no button and loads no script when the client id is null", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: null });
    await mount();
    expect(api.getGoogleConfig).toHaveBeenCalledTimes(1);
    expect(gis.load).not.toHaveBeenCalled();
    expect(gis.renderButton).not.toHaveBeenCalled();
  });

  it("asks nothing of Google while coming-soon", async () => {
    site.face = "coming_soon";
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    await mount();
    expect(api.getGoogleConfig).not.toHaveBeenCalled();
    expect(gis.load).not.toHaveBeenCalled();
    expect(container.querySelector('a[href="/register"]')).toBeNull();
  });

  it("a successful callback POSTs the credential and routes like password login", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    api.loginWithGoogle.mockResolvedValue(PARTICIPANT);
    await mount();
    await act(async () => {
      await gisCallback()({ credential: "id-token-from-google" });
    });
    await flush();
    expect(api.loginWithGoogle).toHaveBeenCalledWith("id-token-from-google");
    expect(session.setAccount).toHaveBeenCalledWith(PARTICIPANT);
    expect(container.textContent).toContain("My courses page");
  });

  it("honours the same `from` redirect as password login", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    api.loginWithGoogle.mockResolvedValue(PARTICIPANT);
    await mount({ from: "/courses/ATO" });
    await act(async () => {
      await gisCallback()({ credential: "t" });
    });
    await flush();
    expect(container.textContent).toContain("Course page");
  });

  it("the constant 401 shows one generic line and stays on the page", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    api.loginWithGoogle.mockRejectedValue(
      new ApiError(401, { detail: "Sign in with Google did not succeed" })
    );
    await mount();
    await act(async () => {
      await gisCallback()({ credential: "bad" });
    });
    await flush();
    expect(session.setAccount).not.toHaveBeenCalled();
    expect(container.textContent).toContain(GOOGLE_SIGN_IN_FAILED);
    expect(container.querySelector("#login-email")).not.toBeNull();
  });
});
