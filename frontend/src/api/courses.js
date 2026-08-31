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
