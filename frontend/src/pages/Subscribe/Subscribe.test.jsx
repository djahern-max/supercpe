/**
 * 029: the offer page renders the price from the payload, the credit
 * line only when it is positive, the two policy links, and a Subscribe
 * button for a participant or sign-in links for a visitor. No course
 * fact appears.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Subscribe from "./Subscribe.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  getSubscribeOffer: vi.fn(),
  startSubscribe: vi.fn(),
}));
const session = vi.hoisted(() => ({ account: null }));

vi.mock("../../api/subscribe", () => ({
  getSubscribeOffer: api.getSubscribeOffer,
  startSubscribe: api.startSubscribe,
}));
vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: session.account,
    loading: false,
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

const OFFER = {
  price_cents: 14900,
  currency: "usd",
  period_days: 365,
  credit_cents: 0,
  pay_today_cents: 14900,
  subscribed: false,
  registration_policy: {
    kind: "registration",
    label: "Registration and attendance",
    url: "/policies#registration",
    effective_at: "2026-09-12T00:00:00Z",
  },
  refund_policy: {
    kind: "refund",
    label: "Refund and cancellation",
    url: "/policies#refund",
    effective_at: "2026-09-12T00:00:00Z",
  },
};

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

describe("Subscribe page (029)", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.getSubscribeOffer.mockReset().mockResolvedValue(OFFER);
    api.startSubscribe.mockReset();
    session.account = null;
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount() {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/subscribe"]}>
          <Subscribe />
        </MemoryRouter>
      );
    });
    await flush();
  }

  it("renders the price from the payload, the terms, and both policy links; no credit line at zero", async () => {
    session.account = { id: 3, email: "pat@supercpe.test", role: "participant" };
    await mount();
    expect(container.textContent).toContain("$149.00");
    expect(container.textContent).toContain("per year");
    expect(container.textContent).toContain("Renews automatically");
    expect(container.textContent).toContain("Cancel any time");
    expect(container.textContent).not.toContain("credited");
    expect(
      container.querySelector('a[href="/policies#registration"]').textContent
    ).toBe("Registration and attendance policy");
    expect(container.querySelector('a[href="/policies#refund"]').textContent).toBe(
      "Refund and cancellation policy"
    );
    const button = container.querySelector("button");
    expect(button.textContent).toBe("Subscribe");
    for (const word of ["National Registry", "ATO", "Account Takeover"]) {
      expect(container.textContent).not.toContain(word);
    }
  });

  it("renders the credit line when the payload carries a credit", async () => {
    session.account = { id: 3, email: "pat@supercpe.test", role: "participant" };
    api.getSubscribeOffer.mockResolvedValue({
      ...OFFER,
      credit_cents: 5800,
      pay_today_cents: 9100,
    });
    await mount();
    expect(container.textContent).toContain(
      "Your $58.00 in course purchases is credited: you pay $91.00 today."
    );
  });

  it("a visitor sees sign-in links instead of the button", async () => {
    await mount();
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector('a[href="/login"]')).not.toBeNull();
    expect(container.querySelector('a[href="/register"]')).not.toBeNull();
    expect(container.textContent).toContain("$149.00");
  });

  it("a current subscriber is pointed at the account page", async () => {
    session.account = { id: 3, email: "pat@supercpe.test", role: "participant" };
    api.getSubscribeOffer.mockResolvedValue({ ...OFFER, subscribed: true });
    await mount();
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector('a[href="/account"]')).not.toBeNull();
  });

  it("the button starts checkout and shows the server's refusal lines", async () => {
    const { ApiError } = await import("../../api/client");
    session.account = { id: 3, email: "pat@supercpe.test", role: "participant" };
    api.startSubscribe.mockRejectedValue(
      new ApiError(422, { errors: ["you already have a current subscription"] })
    );
    await mount();
    act(() => {
      container.querySelector("button").dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    await flush();
    expect(api.startSubscribe).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("already have a current subscription");
  });
});
