import { request } from "./client";

function authHeaders(token) {
  return { "X-Admin-Token": token };
}

export function uploadPackage(file, token) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/v1/admin/packages", {
    method: "POST",
    body,
    headers: authHeaders(token),
  });
}

export function listPackages(token) {
  return request("/api/v1/admin/packages", { headers: authHeaders(token) });
}

export function getPackage(id, token) {
  return request(`/api/v1/admin/packages/${id}`, { headers: authHeaders(token) });
}

export function getTranscript(id, token) {
  return request(`/api/v1/admin/packages/${id}/transcript`, {
    headers: authHeaders(token),
  });
}
