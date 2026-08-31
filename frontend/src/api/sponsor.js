import { request } from "./client";

export function getSponsor() {
  return request("/api/v1/admin/sponsor");
}

export function updateSponsor(data) {
  return request("/api/v1/admin/sponsor", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function setStateRegistrations(rows) {
  return request("/api/v1/admin/sponsor/state-registrations", {
    method: "PUT",
    body: JSON.stringify(rows),
  });
}

// 017: proves the configured email backend before the open flip — the
// OPERATIONS.md runbook step. Sends to the requesting admin's own email.
export function sendTestEmail() {
  return request("/api/v1/admin/email/test", { method: "POST", body: "{}" });
}
