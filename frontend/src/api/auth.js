import { request } from "./client";

export function login(email, password) {
  return request("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return request("/api/v1/auth/logout", { method: "POST", body: "{}" });
}

export function logoutAll() {
  return request("/api/v1/auth/logout-all", { method: "POST", body: "{}" });
}

export function getMe() {
  return request("/api/v1/auth/me");
}

// 020: the participant's state of licensure — their claim, no
// verification step. Send null (or "") to clear it.
export function getMyState() {
  return request("/api/v1/auth/me/state");
}

export function setMyState(state) {
  return request("/api/v1/auth/me/state", {
    method: "PUT",
    body: JSON.stringify({ state: state || null }),
  });
}

export function changePassword(currentPassword, newPassword) {
  return request("/api/v1/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}
