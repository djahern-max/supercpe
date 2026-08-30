export const baseUrl = import.meta.env.VITE_API_URL;

// The play payload's video_url is relative when LocalStorage serves the
// video through the backend's /media/ route, and absolute once Spaces
// hands out presigned URLs (012).
export function resolveMediaUrl(url) {
  return url.startsWith("http") ? url : `${baseUrl}${url}`;
}

export class ApiError extends Error {
  constructor(status, data) {
    super(`API error ${status}`);
    this.status = status;
    this.data = data;
  }
}

export async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    // The session lives in an HttpOnly cookie; every request carries it.
    credentials: "include",
    headers: {
      Accept: "application/json",
      // The browser sets the multipart boundary itself for FormData.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, data);
  }
  return data;
}
