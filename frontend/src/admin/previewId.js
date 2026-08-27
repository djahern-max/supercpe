const STORAGE_KEY = "supercpe_preview_id";

// An opaque identity for preview assessment attempts, generated once per
// browser session and sent as the X-Preview-Id header. Feature 010 replaces
// this with the enrollment id for participants; the preview path stays for
// admins.
export function getPreviewId() {
  let id = sessionStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}
