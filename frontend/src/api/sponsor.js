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
