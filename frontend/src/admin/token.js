// The admin token lives in memory only, for the current tab session.
// Deliberately not localStorage: closing the tab forgets it.
let adminToken = null;

export function getToken() {
  return adminToken;
}

export function setToken(value) {
  adminToken = value;
}

export function clearToken() {
  adminToken = null;
}
