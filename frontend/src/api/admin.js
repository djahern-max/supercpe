import { getPreviewId } from "../admin/previewId";
import { request } from "./client";

function authHeaders(token) {
  return { "X-Admin-Token": token };
}

function previewHeaders(token) {
  return { "X-Admin-Token": token, "X-Preview-Id": getPreviewId() };
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

export function deletePackage(id, token) {
  return request(`/api/v1/admin/packages/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}

export function listCourses(token) {
  return request("/api/v1/admin/courses", { headers: authHeaders(token) });
}

export function createCourse(body, token) {
  return request("/api/v1/admin/courses", {
    method: "POST",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function getCourse(code, token) {
  return request(`/api/v1/admin/courses/${code}`, { headers: authHeaders(token) });
}

export function updateCourse(code, body, token) {
  return request(`/api/v1/admin/courses/${code}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function deleteCourse(code, token) {
  return request(`/api/v1/admin/courses/${code}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}

export function attachLesson(code, body, token) {
  return request(`/api/v1/admin/courses/${code}/lessons`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function detachLesson(code, packageId, token) {
  return request(`/api/v1/admin/courses/${code}/lessons/${packageId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}

export function moveLesson(code, packageId, direction, token) {
  return request(`/api/v1/admin/courses/${code}/lessons/${packageId}/move`, {
    method: "POST",
    body: JSON.stringify({ direction }),
    headers: authHeaders(token),
  });
}

export function recomputeCredit(code, token) {
  return request(`/api/v1/admin/courses/${code}/credit/recompute`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function getPlayLesson(code, packageId, token) {
  return request(`/api/v1/courses/${code}/lessons/${packageId}/play`, {
    headers: authHeaders(token),
  });
}

export function gradeReview(code, packageId, questionKey, choiceKey, token) {
  return request(
    `/api/v1/courses/${code}/lessons/${packageId}/review/${questionKey}`,
    {
      method: "POST",
      body: JSON.stringify({ choice_key: choiceKey }),
      headers: authHeaders(token),
    }
  );
}

export function getAssessment(code, token) {
  return request(`/api/v1/courses/${code}/assessment`, {
    headers: previewHeaders(token),
  });
}

export function startAssessmentAttempt(code, token) {
  return request(`/api/v1/courses/${code}/assessment/attempts`, {
    method: "POST",
    headers: previewHeaders(token),
  });
}

export function saveAssessmentAnswers(code, attemptId, answers, token) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}/answers`, {
    method: "PUT",
    body: JSON.stringify({ answers }),
    headers: previewHeaders(token),
  });
}

export function submitAssessmentAttempt(code, attemptId, answers, token) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
    headers: previewHeaders(token),
  });
}

export function getAssessmentAttempt(code, attemptId, token) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}`, {
    headers: previewHeaders(token),
  });
}

export function listAttempts(code, token) {
  return request(`/api/v1/admin/courses/${code}/attempts`, {
    headers: authHeaders(token),
  });
}

export function updateLessonVersion(code, packageId, newPackageId, token) {
  return request(
    `/api/v1/admin/courses/${code}/lessons/${packageId}/update-version`,
    {
      method: "POST",
      body: JSON.stringify({ new_package_id: newPackageId }),
      headers: authHeaders(token),
    }
  );
}

export function listSmes(token) {
  return request("/api/v1/admin/smes", { headers: authHeaders(token) });
}

export function createSme(body, token) {
  return request("/api/v1/admin/smes", {
    method: "POST",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function updateSme(id, body, token) {
  return request(`/api/v1/admin/smes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function deleteSme(id, token) {
  return request(`/api/v1/admin/smes/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}

export function setCourseDeveloper(code, smeId, usedTechnology, token) {
  return request(`/api/v1/admin/courses/${code}/developer`, {
    method: "PUT",
    body: JSON.stringify({ sme_id: smeId, used_technology: usedTechnology }),
    headers: authHeaders(token),
  });
}

export function recordCourseReview(code, body, token) {
  return request(`/api/v1/admin/courses/${code}/reviews`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: authHeaders(token),
  });
}

export function setCourseReviewCycle(code, reviewCycle, token) {
  return request(`/api/v1/admin/courses/${code}/review-cycle`, {
    method: "PUT",
    body: JSON.stringify({ review_cycle: reviewCycle }),
    headers: authHeaders(token),
  });
}

export function publishCourse(code, token) {
  return request(`/api/v1/admin/courses/${code}/publish`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function unpublishCourse(code, token) {
  return request(`/api/v1/admin/courses/${code}/unpublish`, {
    method: "POST",
    headers: authHeaders(token),
  });
}
