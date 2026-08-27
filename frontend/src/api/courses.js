import { request } from "./client";

export function listPublicCourses() {
  return request("/api/v1/courses");
}

export function getPublicCourse(code) {
  return request(`/api/v1/courses/${code}`);
}
