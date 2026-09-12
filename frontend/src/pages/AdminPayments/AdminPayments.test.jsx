/**
 * 026: /admin/payments shows Stripe's own `livemode` per row — a quiet
 * "Test" marker on a test-mode transaction, none on a live one, none on a
 * row older than the column — and the dashboard link opens the mode the
 * id actually lives in, so a test id never 404s in the live dashboard.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminPayments from "./AdminPayments.jsx";
import { stripeDashboardUrl } from "./stripeDashboard";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  listPayments: vi.fn(),
  voidEnrollment: vi.fn(),
}));

vi.mock("../../api/admin", async (importOriginal) => ({
  ...(await importOriginal()),
  listPayments: api.listPayments,
  voidEnrollment: api.voidEnrollment,
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
    email: "cpa@example.com",
    display_name: "Pat Smith",
    course_code: "GOLD",
    amount_cents: 4900,
    currency: "usd",
    status: "paid",
    stripe_checkout_session_id: "cs_test_abcdefghijklmnopqrstuvwxyz",
    stripe_payment_intent_id: "pi_1",
    livemode: false,
    created_at: "2026-09-11T12:00:00Z",
    updated_at: "2026-09-11T12:00:00Z",
    enrollment_id: 7,
    enrollment_status: "active",
    refunded_with_active_enrollment: false,
    ...overrides,
  };
}

describe("AdminPayments livemode", () => {
  let container;
  let root;

  async function mount(payments) {
    api.listPayments.mockResolvedValue(payments);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/admin/payments"]}>
          <AdminPayments />
        </MemoryRouter>
      );
    });
  }

  beforeEach(() => {
    api.listPayments.mockReset();
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("marks a test-mode row quietly and links it into the sandbox", async () => {
    await mount([row({ id: 1, livemode: false, stripe_payment_intent_id: "pi_test" })]);
    const cells = [...container.querySelectorAll("td")];
    const marker = cells.flatMap((td) => [...td.querySelectorAll("span")]).find(
      (span) => span.textContent === "Test"
    );
    expect(marker).toBeTruthy();
    const link = container.querySelector("a[href*='pi_test']");
    expect(link.getAttribute("href")).toBe(
      "https://dashboard.stripe.com/test/payments/pi_test"
    );
  });

  it("marks nothing on a live row or a row older than the column", async () => {
    await mount([
      row({ id: 1, livemode: true, stripe_payment_intent_id: "pi_live" }),
      row({ id: 2, livemode: null, stripe_payment_intent_id: "pi_old" }),
    ]);
    const spans = [...container.querySelectorAll("td span")];
    expect(spans.some((span) => span.textContent === "Test")).toBe(false);
    expect(container.querySelector("a[href*='pi_live']").getAttribute("href")).toBe(
      "https://dashboard.stripe.com/payments/pi_live"
    );
    expect(container.querySelector("a[href*='pi_old']").getAttribute("href")).toBe(
      "https://dashboard.stripe.com/payments/pi_old"
    );
  });

  it("builds the dashboard URL from livemode alone", () => {
    expect(stripeDashboardUrl({ livemode: false, stripe_payment_intent_id: "pi_a" })).toBe(
      "https://dashboard.stripe.com/test/payments/pi_a"
    );
    expect(stripeDashboardUrl({ livemode: true, stripe_payment_intent_id: "pi_b" })).toBe(
      "https://dashboard.stripe.com/payments/pi_b"
    );
    expect(stripeDashboardUrl({ livemode: null, stripe_payment_intent_id: "pi_c" })).toBe(
      "https://dashboard.stripe.com/payments/pi_c"
    );
  });
});
