/**
 * 030: the register page offers "sign up with Google" under the same
 * rule as the sign-in page — open, and a client id — and a successful
 * callback lands the new participant on their courses.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Register from "./Register.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  register: vi.fn(),
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

vi.mock("../../api/register", () => ({ register: api.register }));
vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal()),
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

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

describe("Register page: sign up with Google (030)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.register.mockReset();
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

  async function mount() {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/register"]}>
          <Routes>
            <Route path="/register" element={<Register />} />
            <Route path="/my/courses" element={<p>My courses page</p>} />
          </Routes>
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("renders the sign-up wording of the button at open with a client id", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    await mount();
    expect(gis.renderButton).toHaveBeenCalledTimes(1);
    expect(gis.renderButton.mock.calls[0][1].text).toBe("signup_with");
    expect(container.textContent).toContain("or");
    expect(container.querySelector("#register-password")).not.toBeNull();
  });

  it("renders no button when the client id is null", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: null });
    await mount();
    expect(gis.load).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain(" or");
  });

  it("a successful callback signs the new participant in and routes home", async () => {
    api.getGoogleConfig.mockResolvedValue({ client_id: "cid.apps" });
    const account = {
      id: 9,
      email: "new@example.test",
      role: "participant",
      display_name: "New Person",
      must_change_password: false,
      subscription_current: false,
      signin_methods: ["google"],
    };
    api.loginWithGoogle.mockResolvedValue(account);
    await mount();
    const { callback } = gis.initialize.mock.calls[0][0];
    await act(async () => {
      await callback({ credential: "id-token" });
    });
    await flush();
    expect(api.loginWithGoogle).toHaveBeenCalledWith("id-token");
    expect(api.register).not.toHaveBeenCalled();
    expect(session.setAccount).toHaveBeenCalledWith(account);
    expect(container.textContent).toContain("My courses page");
  });
});
