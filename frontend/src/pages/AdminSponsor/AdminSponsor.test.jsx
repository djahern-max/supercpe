/**
 * 032: the Certificate card on /admin/sponsor — logo upload, clear, and
 * the preview link call the right routes.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminSponsor from "./AdminSponsor.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getSponsor: vi.fn(),
  uploadSponsorLogo: vi.fn(),
  clearSponsorLogo: vi.fn(),
  getAdminPolicies: vi.fn(),
  getSite: vi.fn(),
  listSiteModeChanges: vi.fn(),
}));

vi.mock("../../api/sponsor", async (importOriginal) => ({
  ...(await importOriginal()),
  getSponsor: api.getSponsor,
  uploadSponsorLogo: api.uploadSponsorLogo,
  clearSponsorLogo: api.clearSponsorLogo,
}));

vi.mock("../../api/admin", async (importOriginal) => ({
  ...(await importOriginal()),
  getAdminPolicies: api.getAdminPolicies,
}));

vi.mock("../../api/site", async (importOriginal) => ({
  ...(await importOriginal()),
  getSite: api.getSite,
  listSiteModeChanges: api.listSiteModeChanges,
}));

// One session object for the whole file: the page keys its load effects
// on `refresh`, so a fresh function per render would remount forever.
const session = vi.hoisted(() => ({
  account: { id: 1, email: "admin@supercpe.test", role: "admin" },
  refresh: () => {},
  signOut: () => {},
}));

vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => session,
}));

function profile(overrides) {
  return {
    name: "superCPE",
    legal_name: "RYZE.AI LLC",
    registry_status: "not_registered",
    national_registry_id: "",
    website: "",
    contact_email: "",
    contact_phone: "",
    address: "",
    other_certificate_statements: "",
    logo_path: null,
    updated_at: "2026-09-13T12:00:00Z",
    missing_fields: ["national_registry_id", "registry_status"],
    missing_for_issuance: [],
    may_claim_registry: false,
    state_registrations: [],
    findings: [],
    launch_findings: [],
    ...overrides,
  };
}

describe("AdminSponsor: the certificate card (032)", () => {
  let container;
  let root;

  async function mount(data) {
    api.getSponsor.mockResolvedValue(data);
    // The other cards on the page load their own data; give them
    // something quiet so an unmocked call cannot throw inside an effect.
    api.getAdminPolicies.mockResolvedValue({ history: [] });
    api.getSite.mockResolvedValue({ site_mode: "coming_soon" });
    api.listSiteModeChanges.mockResolvedValue([]);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminSponsor />
        </MemoryRouter>
      );
    });
  }

  function button(label) {
    return Array.from(container.querySelectorAll("button")).find(
      (el) => el.textContent === label
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  it("links Preview certificate to the admin preview route", async () => {
    await mount(profile());
    const link = Array.from(container.querySelectorAll("a")).find(
      (el) => el.textContent === "Preview certificate"
    );
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toMatch(
      /\/api\/v1\/admin\/sponsor\/certificate-preview\.pdf$/
    );
    expect(link.getAttribute("target")).toBe("_blank");
    // No logo: the monogram is named, and there is nothing to clear.
    expect(container.textContent).toContain("superCPE monogram");
    expect(button("Clear logo")).toBeUndefined();
  });

  it("uploads the chosen file through the logo route", async () => {
    await mount(profile());
    const upload = button("Upload logo");
    expect(upload.disabled).toBe(true);

    const file = new File([new Uint8Array([137, 80, 78, 71])], "logo.png", {
      type: "image/png",
    });
    const input = container.querySelector("#sponsor-logo-file");
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file], configurable: true });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(upload.disabled).toBe(false);

    api.uploadSponsorLogo.mockResolvedValue(
      profile({ logo_path: "sponsor/logo.png" })
    );
    await act(async () => {
      upload.click();
    });
    expect(api.uploadSponsorLogo).toHaveBeenCalledWith(file);
    expect(container.textContent).toContain("sponsor/logo.png");
    expect(button("Clear logo")).toBeTruthy();
  });

  it("clears the logo through the logo route", async () => {
    await mount(profile({ logo_path: "sponsor/logo.svg" }));
    api.clearSponsorLogo.mockResolvedValue(profile());
    await act(async () => {
      button("Clear logo").click();
    });
    expect(api.clearSponsorLogo).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("superCPE monogram");
    expect(button("Clear logo")).toBeUndefined();
  });

  it("shows the server's refusal on a bad upload", async () => {
    const { ApiError } = await import("../../api/client");
    await mount(profile());
    const file = new File(["nope"], "photo.jpg", { type: "image/jpeg" });
    const input = container.querySelector("#sponsor-logo-file");
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file], configurable: true });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    api.uploadSponsorLogo.mockRejectedValue(
      new ApiError(422, { errors: ["The logo must be a PNG or an SVG file; the upload was neither."] })
    );
    await act(async () => {
      button("Upload logo").click();
    });
    expect(container.textContent).toContain("PNG or an SVG");
  });
});
