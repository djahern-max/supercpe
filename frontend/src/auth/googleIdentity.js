// 030: Google Identity Services, loaded once and lazily. Only the sign-in
// and register pages call this, and only after /auth/google/config has
// answered with a client id — so a coming-soon page, an admin page, or
// an unconfigured site never makes a request to Google. Never put the
// script tag in index.html.
export const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

let pending = null;

function gisGlobal() {
  return window.google?.accounts?.id ?? null;
}

/** Resolves with `window.google.accounts.id` once the script has run. */
export function loadGoogleIdentity() {
  const ready = gisGlobal();
  if (ready) return Promise.resolve(ready);
  if (!pending) {
    pending = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GIS_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => {
        const loaded = gisGlobal();
        if (loaded) {
          resolve(loaded);
        } else {
          pending = null;
          reject(new Error("Google Identity Services did not initialize"));
        }
      };
      script.onerror = () => {
        pending = null;
        script.remove();
        reject(new Error("Google Identity Services failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return pending;
}
