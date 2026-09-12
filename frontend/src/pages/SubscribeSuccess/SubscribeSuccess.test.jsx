/**
 * 029: the success page polls the session's status until the webhook
 * makes the subscription current, then lands with a link to the catalog
 * and refreshes the session (the header's Subscribe link keys on it).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SubscribeSuccess from "./SubscribeSuccess.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ getSubscribeStatus: vi.fn() }));
const session = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock("../../api/subscribe", () => ({
  getSubscribeStatus: api.getSubscribeStatus,
}));
vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: { id: 3, email: "pat@supercpe.test", role: "participant" },
    loading: false,
    refresh: session.refresh,
    signOut: vi.fn(),
  }),
}));

const PENDING = {
  status: "incomplete",
  current: false,
  credit_applied_cents: 0,
  current_period_end: null,
  support_email: "help@example.com",
};
const CURRENT = {
  status: "active",
  current: true,
  credit_applied_cents: 5800,
  current_period_end: "2027-09-12T00:00:00Z",
  support_email: "help@example.com",
};

describe("SubscribeSuccess (029)", () => {
  let container;
  let root;

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    api.getSubscribeStatus.mockReset();
    session.refresh.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
  });

  async function mount(path) {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={[path]}>
          <SubscribeSuccess />
        </MemoryRouter>
      );
    });
  }

  it("polls until the subscription is current, then lands", async () => {
    api.getSubscribeStatus
      .mockResolvedValueOnce(PENDING)
      .mockResolvedValueOnce(CURRENT);
    await mount("/subscribe/success?session_id=cs_sub_1");
    expect(container.textContent).toContain("Confirming your subscription");
    expect(api.getSubscribeStatus).toHaveBeenCalledWith("cs_sub_1");
    expect(session.refresh).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(api.getSubscribeStatus).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("You're subscribed");
    expect(container.textContent).toContain("$58.00 of prior course purchases was credited");
    expect(container.querySelector('a[href="/courses"]').textContent).toBe(
      "Choose a course"
    );
    expect(session.refresh).toHaveBeenCalledTimes(1);

    // Landed: no further polling.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.getSubscribeStatus).toHaveBeenCalledTimes(2);
  });

  it("without a session id, says the subscription could not be looked up", async () => {
    await mount("/subscribe/success");
    expect(container.textContent).toContain("could not be looked up");
    expect(api.getSubscribeStatus).not.toHaveBeenCalled();
  });
});
