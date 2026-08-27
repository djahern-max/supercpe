import { request } from "./client";

export function getHealth() {
  return request("/api/v1/health");
}
