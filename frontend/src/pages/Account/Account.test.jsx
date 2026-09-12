/**
 * 029: the account page's Subscription section states each of the
 * derived states in words and offers Manage subscription (the Stripe
 * Customer Portal) whenever a Customer exists.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Account from "./Account.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getMyState: vi.fn(),
  setMyState: vi.fn(),
  getMySubscription: vi.fn(),
  openSubscriptionPortal: vi.fn(),
}));

vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal()),
  getMyState: api.getMyState,
  setMyState: api.setMyState,
}));
vi.mock("../../api/subscribe", () => ({
  getMySubscription: api.getMySubscription,
  openSubscriptionPortal: api.openSubscriptionPortal,
}));
vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: { id: 3, email: "pat@supercpe.test", role: "participant" },
    loading: false,
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

function subscription(overrides = {}) {
  return {
    state: "none",
    status: null,
    current_period_end: null,
    cancel_at_period_end: false,
    canceled_at: null,
    credit_applied_cents: 0,
    manageable: false,
    ...overrides,
  };
}

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

function manageButton() {
  return Array.from(document.querySelectorAll("button")).find((b) =>
    /Manage subscription|Update payment method/.test(b.textContent)
  );
}

describe("Account subscription section (029)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.getMyState.mockResolvedValue({ state: null });
    api.getMySubscription.mockReset();
    api.openSubscriptionPortal.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(payload) {
    api.getMySubscription.mockResolvedValue(payload);
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/account"]}>
          <Account />
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("none: a link to subscribe, no manage button", async () => {
    await mount(subscription());
    expect(container.textContent).toContain("You do not have a subscription.");
    expect(container.querySelector('a[href="/subscribe"]')).not.toBeNull();
    expect(manageButton()).toBeUndefined();
  });

  it("current: renews on the date, credit consumed, manage button", async () => {
    await mount(
      subscription({
        state: "current",
        status: "active",
        current_period_end: "2027-09-12T00:00:00Z",
        credit_applied_cents: 5800,
        manageable: true,
      })
    );
    expect(container.textContent).toContain("Your subscription is current and renews on");
    expect(container.textContent).toContain("2027");
    expect(container.textContent).toContain(
      "$58.00 of prior course purchases was credited"
    );
    expect(manageButton().textContent).toBe("Manage subscription");
  });

  it("cancels at period end: says so with the date", async () => {
    await mount(
      subscription({
        state: "cancels_at_period_end",
        status: "active",
        cancel_at_period_end: true,
        current_period_end: "2027-09-12T00:00:00Z",
        manageable: true,
      })
    );
    expect(container.textContent).toContain("cancels on");
    expect(container.textContent).toContain("you keep access until then");
  });

  it("past due: the update-payment-method button opens the portal", async () => {
    await mount(
      subscription({ state: "past_due", status: "past_due", manageable: true })
    );
    expect(container.textContent).toContain("Your last subscription payment failed.");
    const button = manageButton();
    expect(button.textContent).toBe("Update payment method");
    api.openSubscriptionPortal.mockResolvedValue({
      url: "https://billing.stripe.com/p/session/test_1",
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    act(() => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(api.openSubscriptionPortal).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("https://billing.stripe.com/p/session/test_1");
    vi.unstubAllGlobals();
  });

  it("lapsed: records are kept, subscribe again", async () => {
    await mount(
      subscription({
        state: "lapsed",
        status: "canceled",
        current_period_end: "2026-09-01T00:00:00Z",
        manageable: true,
      })
    );
    expect(container.textContent).toContain("Your subscription has ended");
    expect(container.textContent).toContain("Your courses and certificates are kept.");
    expect(container.querySelector('a[href="/subscribe"]').textContent).toBe(
      "Subscribe again"
    );
  });
});
