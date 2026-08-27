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
