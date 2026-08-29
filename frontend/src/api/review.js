import { request } from "./client";

export function listReviewCourses() {
  return request("/api/v1/review/courses");
}

export function getReviewCourse(code) {
  return request(`/api/v1/review/courses/${code}`);
}

export function recordReview(code, body) {
  return request(`/api/v1/review/courses/${code}/reviews`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
