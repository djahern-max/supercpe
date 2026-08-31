import { request } from "./client";

// 019: the public verification lookup. Unknown and malformed codes both
// answer plain 404; the page shows one not-found message for either.
export function verifyCertificate(code) {
  return request(`/api/v1/certificates/verify/${encodeURIComponent(code)}`);
}
