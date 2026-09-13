/**
 * 030a: /admin/accounts shows two read-only columns the server derives —
 * when the address was verified (or "—" while it is not) and how the
 * account signs in (Password / Google / Password and Google) — for the
 * three sign-in variants. No filter, no edit.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminAccounts from "./AdminAccounts.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ listAccounts: vi.fn() }));

vi.mock("../../api/accounts", async (importOriginal) => ({
  ...(await importOriginal()),
  listAccounts: api.listAccounts,
}));

vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: { id: 1, email: "admin@supercpe.test", role: "admin" },
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

function row(overrides) {
  return {
    id: 1,
    email: "admin@supercpe.test",
    role: "admin",
    display_name: "",
    is_active: true,
    must_change_password: false,
    created_at: "2026-09-01T12:00:00Z",
    deactivated_at: null,
    last_sign_in: null,
    open_sessions: 0,
    email_verified_at: "2026-09-01T12:00:00Z",
    signin_methods: ["password"],
    ...overrides,
  };
}

const ROWS = [
  row(),
  row({
    id: 2,
    email: "g@example.test",
    role: "participant",
    email_verified_at: "2026-09-12T09:30:00Z",
    signin_methods: ["google"],
  }),
  row({
    id: 3,
    email: "both@example.test",
    role: "participant",
    signin_methods: ["password", "google"],
  }),
  row({
    id: 4,
    email: "unverified@example.test",
    role: "participant",
    email_verified_at: null,
    signin_methods: ["password"],
  }),
];

describe("AdminAccounts: verification and sign-in columns (030a)", () => {
  let container;
  let root;

  async function mount(accounts) {
    api.listAccounts.mockResolvedValue(accounts);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/admin/accounts"]}>
          <AdminAccounts />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  const cells = (email) => {
    const tr = Array.from(container.querySelectorAll("tbody tr")).find((r) =>
      r.textContent.includes(email)
    );
    return Array.from(tr.querySelectorAll("td")).map((td) => td.textContent);
  };

  beforeEach(() => {
    api.listAccounts.mockReset();
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("has a Verified and a Sign-in column", async () => {
    await mount(ROWS);
    const headers = Array.from(container.querySelectorAll("thead th")).map(
      (th) => th.textContent
    );
    expect(headers).toEqual([
      "Email",
      "Role",
      "Active",
      "Verified",
      "Sign-in",
      "Last sign-in",
      "Open sessions",
      "",
    ]);
  });

  it("renders the three sign-in variants and the unverified dash", async () => {
    await mount(ROWS);
    // Columns: email, role, active, verified, sign-in, last sign-in, ...
    expect(cells("admin@supercpe.test")[4]).toBe("Password");
    expect(cells("g@example.test")[4]).toBe("Google");
    expect(cells("both@example.test")[4]).toBe("Password and Google");
    expect(cells("unverified@example.test")[4]).toBe("Password");

    expect(cells("g@example.test")[3]).toBe(
      new Date("2026-09-12T09:30:00Z").toLocaleDateString()
    );
    expect(cells("unverified@example.test")[3]).toBe("—");
    expect(cells("admin@supercpe.test")[3]).not.toBe("—");
  });

  it("reads a row from before the columns existed as password-only", async () => {
    const legacy = row({ id: 9, email: "old@example.test" });
    delete legacy.signin_methods;
    delete legacy.email_verified_at;
    await mount([legacy]);
    expect(cells("old@example.test")[3]).toBe("—");
    expect(cells("old@example.test")[4]).toBe("Password");
  });
});
