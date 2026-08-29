import { request } from "./client";

export function getSite() {
  return request("/api/v1/site");
}

export function setSiteMode(siteMode, note) {
  return request("/api/v1/admin/site-mode", {
    method: "PUT",
    body: JSON.stringify({ site_mode: siteMode, note }),
  });
}

export function listSiteModeChanges() {
  return request("/api/v1/admin/site-mode/changes");
}
