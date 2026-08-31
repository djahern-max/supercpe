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

// 021: the invitations. Send refuses while coming_soon (the service
// says why); re-running it skips every sent row, so the same button is
// the retry. Resend is the per-row recovery for a failed row.
export function sendInvitations() {
  return request("/api/v1/admin/waiting-list/invitations", {
    method: "POST",
  });
}

export function resendInvitation(id) {
  return request(`/api/v1/admin/waiting-list/${id}/resend`, {
    method: "POST",
  });
}

// A plain top-level navigation: the session cookie is SameSite=Lax, so
// it rides along and the browser saves the file.
export const waitingListCsvUrl = `${baseUrl}/api/v1/admin/waiting-list/export.csv`;
