import { request } from "./client";

function authHeaders(token) {
  return { "X-Admin-Token": token };
}

export function getSponsor(token) {
  return request("/api/v1/admin/sponsor", { headers: authHeaders(token) });
}

export function updateSponsor(token, data) {
  return request("/api/v1/admin/sponsor", {
    method: "PUT",
    body: JSON.stringify(data),
    headers: authHeaders(token),
  });
}

export function setStateRegistrations(token, rows) {
  return request("/api/v1/admin/sponsor/state-registrations", {
    method: "PUT",
    body: JSON.stringify(rows),
    headers: authHeaders(token),
  });
}
