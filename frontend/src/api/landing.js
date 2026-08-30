import { baseUrl, request } from "./client";

// Both public calls exist only while site_mode is coming_soon (015);
// they 404 once the site opens.
export function getLanding() {
  return request("/api/v1/landing");
}

export function joinWaitingList(body) {
  return request("/api/v1/waiting-list", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Admin surface.
export function listWaitingList() {
  return request("/api/v1/admin/waiting-list");
}

export function removeWaitingListEntry(id, reason) {
  return request(`/api/v1/admin/waiting-list/${id}/remove`, {
    method: "POST",
    body: JSON.stringify({ reason: reason || "" }),
  });
}

// A plain top-level navigation: the session cookie is SameSite=Lax, so
// it rides along and the browser saves the file.
export const waitingListCsvUrl = `${baseUrl}/api/v1/admin/waiting-list/export.csv`;
