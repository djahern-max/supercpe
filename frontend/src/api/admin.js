import { getPreviewId } from "../admin/previewId";
import { request } from "./client";

// Assessment previews are keyed to this browser session; the login cookie
// itself rides along automatically (api/client.js).
function previewHeaders() {
  return { "X-Preview-Id": getPreviewId() };
}

export function uploadPackage(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/v1/admin/packages", { method: "POST", body });
}

export function listPackages() {
  return request("/api/v1/admin/packages");
}

export function getPackage(id) {
  return request(`/api/v1/admin/packages/${id}`);
}

export function getTranscript(id) {
  return request(`/api/v1/admin/packages/${id}/transcript`);
}

export function deletePackage(id) {
  return request(`/api/v1/admin/packages/${id}`, { method: "DELETE" });
}

export function listCourses() {
  return request("/api/v1/admin/courses");
}

export function createCourse(body) {
  return request("/api/v1/admin/courses", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getCourse(code) {
  return request(`/api/v1/admin/courses/${code}`);
}

export function updateCourse(code, body) {
  return request(`/api/v1/admin/courses/${code}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteCourse(code) {
  return request(`/api/v1/admin/courses/${code}`, { method: "DELETE" });
}

export function attachLesson(code, body) {
  return request(`/api/v1/admin/courses/${code}/lessons`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function detachLesson(code, packageId) {
  return request(`/api/v1/admin/courses/${code}/lessons/${packageId}`, {
    method: "DELETE",
  });
}

export function moveLesson(code, packageId, direction) {
  return request(`/api/v1/admin/courses/${code}/lessons/${packageId}/move`, {
    method: "POST",
    body: JSON.stringify({ direction }),
  });
}

export function recomputeCredit(code) {
  return request(`/api/v1/admin/courses/${code}/credit/recompute`, {
    method: "POST",
  });
}

export function getPlayLesson(code, packageId) {
  return request(`/api/v1/courses/${code}/lessons/${packageId}/play`);
}

export function gradeReview(code, packageId, questionKey, choiceKey) {
  return request(
    `/api/v1/courses/${code}/lessons/${packageId}/review/${questionKey}`,
    {
      method: "POST",
      body: JSON.stringify({ choice_key: choiceKey }),
    }
  );
}

export function getAssessment(code) {
  return request(`/api/v1/courses/${code}/assessment`, {
    headers: previewHeaders(),
  });
}

export function startAssessmentAttempt(code) {
  return request(`/api/v1/courses/${code}/assessment/attempts`, {
    method: "POST",
    headers: previewHeaders(),
  });
}

export function saveAssessmentAnswers(code, attemptId, answers) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}/answers`, {
    method: "PUT",
    body: JSON.stringify({ answers }),
    headers: previewHeaders(),
  });
}

export function submitAssessmentAttempt(code, attemptId, answers) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
    headers: previewHeaders(),
  });
}

export function getAssessmentAttempt(code, attemptId) {
  return request(`/api/v1/courses/${code}/assessment/attempts/${attemptId}`, {
    headers: previewHeaders(),
  });
}

export function listAttempts(code) {
  return request(`/api/v1/admin/courses/${code}/attempts`);
}

export function updateLessonVersion(code, packageId, newPackageId) {
  return request(
    `/api/v1/admin/courses/${code}/lessons/${packageId}/update-version`,
    {
      method: "POST",
      body: JSON.stringify({ new_package_id: newPackageId }),
    }
  );
}

export function listSmes() {
  return request("/api/v1/admin/smes");
}

export function createSme(body) {
  return request("/api/v1/admin/smes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSme(id, body) {
  return request(`/api/v1/admin/smes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteSme(id) {
  return request(`/api/v1/admin/smes/${id}`, { method: "DELETE" });
}

export function setCourseDeveloper(code, smeId, usedTechnology) {
  return request(`/api/v1/admin/courses/${code}/developer`, {
    method: "PUT",
    body: JSON.stringify({ sme_id: smeId, used_technology: usedTechnology }),
  });
}

export function recordCourseReview(code, body) {
  return request(`/api/v1/admin/courses/${code}/reviews`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function setCourseReviewCycle(code, reviewCycle) {
  return request(`/api/v1/admin/courses/${code}/review-cycle`, {
    method: "PUT",
    body: JSON.stringify({ review_cycle: reviewCycle }),
  });
}

export function listEnrollments(code) {
  return request(`/api/v1/admin/courses/${code}/enrollments`);
}

export function enrollParticipant(code, email) {
  return request(`/api/v1/admin/courses/${code}/enrollments`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function listCompletions(code) {
  return request(`/api/v1/admin/courses/${code}/completions`);
}

export function renderCertificate(completionId) {
  return request(`/api/v1/admin/completions/${completionId}/render`, {
    method: "POST",
  });
}

export function adminCertificateUrl(completionId) {
  const baseUrl = import.meta.env.VITE_API_URL;
  return `${baseUrl}/api/v1/admin/completions/${completionId}/certificate.pdf`;
}

export function publishCourse(code) {
  return request(`/api/v1/admin/courses/${code}/publish`, { method: "POST" });
}

export function unpublishCourse(code) {
  return request(`/api/v1/admin/courses/${code}/unpublish`, { method: "POST" });
}
