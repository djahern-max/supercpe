import { request } from "./client";

export function listPublicCourses() {
  return request("/api/v1/courses");
}

export function getPublicCourse(code) {
  return request(`/api/v1/courses/${code}`);
}

// 020: per-viewer, so a separate call from the cacheable public payload.
// 404 is the normal answer for anyone the hint does not apply to.
export function getJurisdictionNote(code) {
  return request(`/api/v1/courses/${code}/jurisdiction-note`);
}

// 028: a new one-year enrollment at no charge for a participant who paid
// for the course and did not complete it before the year ran out. No
// Stripe page: the answer is the enrollment card, or a 422 saying why not.
export function renewCourse(code) {
  return request(`/api/v1/courses/${code}/renew`, { method: "POST" });
}
