import { useEffect, useState } from "react";
import { getSite } from "../../api/site";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./SiteGate.module.css";

/**
 * Wraps the public pages. While site_mode is coming_soon and nobody is
 * signed in, renders the one-sentence placeholder — deliberately nothing
 * else: no link to /login, and never a word about the Registry (only
 * /api/v1/site's mode and sponsor name are read).
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

  return (
    <main className={styles.page}>
      <p className={styles.sentence}>
        {site.sponsor_name ? `${site.sponsor_name} — ` : ""}superCPE is not
        yet open.
      </p>
    </main>
  );
}

export default SiteGate;
