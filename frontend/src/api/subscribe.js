import { request } from "./client";

// 029: the annual subscription. The offer is readable by anyone at open
// (a visitor sees sign-in links instead of the button); everything else
// is the signed-in participant's own.
export function getSubscribeOffer() {
  return request("/api/v1/subscribe");
}

export function startSubscribe() {
  return request("/api/v1/subscribe", { method: "POST" });
}

export function getSubscribeStatus(sessionId) {
  return request(`/api/v1/subscribe/${sessionId}/status`);
}

export function getMySubscription() {
  return request("/api/v1/subscribe/me");
}

// The Stripe Customer Portal: cancellation, card update, invoice history
// all live there; superCPE builds none of them.
export function openSubscriptionPortal() {
  return request("/api/v1/subscribe/portal", { method: "POST" });
}

// A current subscriber's enrollment: a click, no Stripe page.
export function enrollWithSubscription(code) {
  return request(`/api/v1/courses/${code}/enroll`, { method: "POST" });
}
