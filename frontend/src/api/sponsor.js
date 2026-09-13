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

// 027: the public subset — name, website, contact address — behind the
// same open-or-session gate as the catalog. The site footer and the
// exhausted re-takes notice read the contact address from here.
export function getPublicSponsor() {
  return request("/api/v1/sponsor");
}

// 032: the certificate mark. PNG or SVG, stored at sponsor/logo.<ext>;
// clearing it returns the certificate to the brand logo (033). Presentation
// only — the snapshot never carries it.
export function uploadSponsorLogo(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/v1/admin/sponsor/logo", { method: "PUT", body });
}

export function clearSponsorLogo() {
  return request("/api/v1/admin/sponsor/logo", { method: "DELETE" });
}

// 032: a sample certificate from the sponsor's facts as they stand,
// rendered on the fly and returned inline — nothing stored, nothing
// issued. Opened in a new tab; the session cookie rides along.
export function certificatePreviewUrl() {
  const baseUrl = import.meta.env.VITE_API_URL;
  return `${baseUrl}/api/v1/admin/sponsor/certificate-preview.pdf`;
}
