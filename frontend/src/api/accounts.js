import { request } from "./client";

export function listAccounts() {
  return request("/api/v1/admin/accounts");
}

export function createAccount(body) {
  return request("/api/v1/admin/accounts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function setAccountRole(id, role) {
  return request(`/api/v1/admin/accounts/${id}/role`, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export function deactivateAccount(id) {
  return request(`/api/v1/admin/accounts/${id}/deactivate`, {
    method: "POST",
    body: "{}",
  });
}

export function reactivateAccount(id) {
  return request(`/api/v1/admin/accounts/${id}/reactivate`, {
    method: "POST",
    body: "{}",
  });
}

export function revokeAccountSessions(id) {
  return request(`/api/v1/admin/accounts/${id}/revoke-sessions`, {
    method: "POST",
    body: "{}",
  });
}
