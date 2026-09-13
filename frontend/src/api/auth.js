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

// 030: Google sign-in. The config is the client id or null — the button
// renders only when it is non-null. The credential is the ID token Google
// handed the browser; the server verifies it and answers exactly the
// shape password login does, or one constant 401 for every refusal.
export function getGoogleConfig() {
  return request("/api/v1/auth/google/config");
}

export function loginWithGoogle(credential) {
  return request("/api/v1/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });
}
