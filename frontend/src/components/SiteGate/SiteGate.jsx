import { useEffect, useState } from "react";
import { getSite } from "../../api/site";
import { useSession } from "../../auth/SessionContext.jsx";
import ComingSoon from "../../pages/ComingSoon/ComingSoon.jsx";

/**
 * Wraps the public pages, and the catch-all route. While site_mode is
 * coming_soon and nobody is signed in, every gated path renders the 015
 * landing page instead of its content — deliberately with no link to
 * /login and never a word about the Registry (the page reads only
 * /api/v1/site and /api/v1/landing).
 */
function SiteGate({ children }) {
  const { account, loading } = useSession();
  const [site, setSite] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getSite()
      .then(setSite)
      .catch(() => setFailed(true));
  }, []);

  // On a failed /site read, fall through to the page; it reports backend
  // trouble in its own words.
  if (failed) return children;
  if (loading || site === null) return null;
  if (site.site_mode === "open" || account) return children;

  return <ComingSoon />;
}

export default SiteGate;
