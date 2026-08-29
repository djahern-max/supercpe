import { request } from "./client";

export function getPolicies() {
  return request("/api/v1/policies");
}

export function getHowItWorks() {
  return request("/api/v1/how-it-works");
}
