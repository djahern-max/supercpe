import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getSite } from "../api/site";
import { useSession } from "../auth/SessionContext.jsx";

const SiteContext = createContext(null);

/**
 * Reads GET /api/v1/site once on boot and shares it, so SiteGate and
 * SiteHeader work from one answer instead of two requests. `loading` is
 * true until the read answers either way; a failed read is not fatal —
 * `failed` is set and consumers fall through, exactly as SiteGate did
 * when it owned the request.
 */
export function SiteProvider({ children }) {
  const [site, setSite] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getSite()
      .then(setSite)
      .catch(() => setFailed(true));
  }, []);

  const value = useMemo(
    () => ({ site, loading: site === null && !failed, failed }),
    [site, failed]
  );

  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSite() {
  return useContext(SiteContext);
}

export const SITE_FACE = {
  LOADING: "loading",
  COMING_SOON: "coming_soon",
  OPEN: "open",
};

/**
 * The one coming-soon decision. While site_mode is coming_soon and nobody
 * is signed in, the public face of the site is the 015/024 landing page
 * and nothing else — SiteGate renders it in place of every gated page,
 * and SiteHeader renders nothing above it (8.01: a "Courses" link over a
 * page deliberately stripped to a wordmark would be a partial disclosure,
 * which 024 recorded as worse than none). Both read this function so the
 * two cannot drift; do not copy the expression into a component.
 *
 * Order matters and matches the original SiteGate: a failed /site read
 * falls through to OPEN before anything else is consulted — the page
 * reports backend trouble in its own words.
 */
export function siteFace(siteState, sessionState) {
  if (siteState.failed) return SITE_FACE.OPEN;
  if (sessionState.loading || siteState.loading) return SITE_FACE.LOADING;
  if (siteState.site.site_mode === "open" || sessionState.account) {
    return SITE_FACE.OPEN;
  }
  return SITE_FACE.COMING_SOON;
}

export function useSiteFace() {
  return siteFace(useSite(), useSession());
}
