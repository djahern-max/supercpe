import { request } from "./client";

const baseUrl = import.meta.env.VITE_API_URL;

export function listMyCourses() {
  return request("/api/v1/my/courses");
}

export function getMyEnrollment(enrollmentId) {
  return request(`/api/v1/my/enrollments/${enrollmentId}`);
}

export function getMyPlayLesson(enrollmentId, packageId) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/lessons/${packageId}/play`
  );
}

export function gradeMyReview(enrollmentId, packageId, questionKey, choiceKey) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/lessons/${packageId}/review/${questionKey}`,
    { method: "POST", body: JSON.stringify({ choice_key: choiceKey }) }
  );
}

export function putMyProgress(enrollmentId, packageId, furthestSeconds) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/lessons/${packageId}/progress`,
    {
      method: "PUT",
      body: JSON.stringify({ furthest_seconds: furthestSeconds }),
    }
  );
}

export function getMyAssessment(enrollmentId) {
  return request(`/api/v1/my/enrollments/${enrollmentId}/assessment`);
}

export function startMyAttempt(enrollmentId) {
  return request(`/api/v1/my/enrollments/${enrollmentId}/assessment/attempts`, {
    method: "POST",
  });
}

export function saveMyAnswers(enrollmentId, attemptId, answers) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/assessment/attempts/${attemptId}/answers`,
    { method: "PUT", body: JSON.stringify({ answers }) }
  );
}

export function submitMyAttempt(enrollmentId, attemptId, answers) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/assessment/attempts/${attemptId}/submit`,
    { method: "POST", body: JSON.stringify({ answers }) }
  );
}

export function getMyAttempt(enrollmentId, attemptId) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/assessment/attempts/${attemptId}`
  );
}

// A plain top-level navigation: the SameSite=Lax session cookie rides
// along, and the browser shows the PDF itself.
export function myCertificateUrl(completionId) {
  return `${baseUrl}/api/v1/my/completions/${completionId}/certificate.pdf`;
}

export function getMyEvaluation(completionId) {
  return request(`/api/v1/my/completions/${completionId}/evaluation`);
}

export function submitMyEvaluation(completionId, ratings, comments) {
  return request(`/api/v1/my/completions/${completionId}/evaluation`, {
    method: "POST",
    body: JSON.stringify({ ratings, comments }),
  });
}

// --- 023: the text reader, its search, and its glossary ---------------------

export function getMyReadLesson(enrollmentId, packageId) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/lessons/${packageId}/read`
  );
}

export function searchMyCourse(enrollmentId, query) {
  return request(
    `/api/v1/my/enrollments/${enrollmentId}/search?q=${encodeURIComponent(query)}`
  );
}

export function getMyGlossary(enrollmentId, term) {
  const suffix = term ? `?term=${encodeURIComponent(term)}` : "";
  return request(`/api/v1/my/enrollments/${enrollmentId}/glossary${suffix}`);
}
