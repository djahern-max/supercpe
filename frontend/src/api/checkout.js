import { request } from "./client";

export function startCheckout(courseCode) {
  return request("/api/v1/checkout", {
    method: "POST",
    body: JSON.stringify({ course_code: courseCode }),
  });
}

export function getCheckoutStatus(sessionId) {
  return request(`/api/v1/checkout/${sessionId}/status`);
}
