import { request } from "./client";

// 017: registration and resend answer one constant message whatever
// happened — the UI shows it verbatim and never guesses at more.
export function register(body) {
  return request("/api/v1/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function verifyEmail(token) {
  return request("/api/v1/verify", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export function resendVerification(email) {
  return request("/api/v1/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}
