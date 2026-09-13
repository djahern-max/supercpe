import { useEffect, useRef, useState } from "react";
import { getGoogleConfig, loginWithGoogle } from "../../api/auth";
import { loadGoogleIdentity } from "../../auth/googleIdentity";
import { SITE_FACE, useSiteFace } from "../../site/SiteContext.jsx";
import styles from "./GoogleSignIn.module.css";

// One line for every failure: the server's 401 is constant and says
// nothing about why, and neither does this.
export const GOOGLE_SIGN_IN_FAILED =
  "Sign in with Google did not succeed. Try again, or use your email and password.";

/**
 * 030: Google's rendered "Sign in with Google" button under an "or"
 * divider. Renders nothing unless the site face is open and the server
 * reports a client id; only then is the GIS script loaded. ID-token
 * flow in a popup — no One Tap, no auto-select, no redirect. On success
 * the caller decides where to go (the login page routes exactly as
 * password login does).
 *
 * `text` is GIS's button wording key: "signin_with" or "signup_with".
 */
function GoogleSignIn({ text = "signin_with", onSuccess }) {
  const face = useSiteFace();
  const open = face === SITE_FACE.OPEN;
  const [clientId, setClientId] = useState(null);
  const [failed, setFailed] = useState(false);
  const buttonRef = useRef(null);
  // GIS holds one callback for the page's lifetime; it reads the latest
  // onSuccess through the ref rather than the one it was initialized with.
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => {
    onSuccessRef.current = onSuccess;
  });

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    getGoogleConfig()
      .then((config) => {
        if (!cancelled) setClientId(config.client_id ?? null);
      })
      .catch(() => {
        // No config, no button — the page works without it.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !clientId) return undefined;
    let cancelled = false;
    loadGoogleIdentity()
      .then((gis) => {
        if (cancelled || !buttonRef.current) return;
        gis.initialize({
          client_id: clientId,
          ux_mode: "popup",
          auto_select: false,
          callback: async (response) => {
            setFailed(false);
            try {
              const account = await loginWithGoogle(response.credential);
              onSuccessRef.current(account);
            } catch {
              setFailed(true);
            }
          },
        });
        gis.renderButton(buttonRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          shape: "rectangular",
          text,
          width: 320,
        });
      })
      .catch(() => {
        // The script did not load; the password form is still there.
      });
    return () => {
      cancelled = true;
    };
  }, [open, clientId, text]);

  if (!open || !clientId) return null;

  return (
    <div className={styles.wrapper}>
      <p className={styles.divider}>
        <span>or</span>
      </p>
      <div ref={buttonRef} className={styles.button} />
      {failed && <p className={styles.error}>{GOOGLE_SIGN_IN_FAILED}</p>}
    </div>
  );
}

export default GoogleSignIn;
