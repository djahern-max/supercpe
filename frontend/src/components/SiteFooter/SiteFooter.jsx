import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { getPublicSponsor } from "../../api/sponsor";
import { SITE_FACE, useSite, useSiteFace } from "../../site/SiteContext.jsx";
import styles from "./SiteFooter.module.css";

/**
 * 027: the site's foot — a second path to the published policies (8.01.1
 * "made available"), the 4.05.3 item 4 instructions page, and the
 * sponsor's contact address. It renders under exactly the header's rule
 * (025): nothing while the site's face is coming-soon, nothing under
 * /admin, nothing on /change-password. It states no course fact, no
 * price, no credit figure, nothing about the Registry, and never reads
 * `may_claim_registry` — the same test the header pins.
 *
 * The contact address comes from the public sponsor payload, which sits
 * behind the same open-or-session gate as the catalog; when that read
 * fails the links render without it. 029: a Subscribe link, only while
 * the site is actually open — the offer is not reachable in coming_soon.
 */
function SiteFooter() {
  const face = useSiteFace();
  const { site } = useSite();
  const { pathname } = useLocation();
  const [contact, setContact] = useState(null);

  const hidden =
    face !== SITE_FACE.OPEN ||
    pathname === "/admin" ||
    pathname.startsWith("/admin/") ||
    pathname === "/change-password";

  useEffect(() => {
    if (hidden) return undefined;
    let cancelled = false;
    getPublicSponsor()
      .then((profile) => {
        if (!cancelled) setContact(profile.contact_email || null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [hidden]);

  if (hidden) return null;

  return (
    <footer className={styles.footer}>
      <nav className={styles.nav} aria-label="Site footer">
        <Link className={styles.link} to="/policies">
          Policies
        </Link>
        <Link className={styles.link} to="/how-it-works">
          How it works
        </Link>
        {site?.site_mode === "open" && (
          <Link className={styles.link} to="/subscribe">
            Subscribe
          </Link>
        )}
        {contact && (
          <a className={styles.link} href={`mailto:${contact}`}>
            {contact}
          </a>
        )}
      </nav>
    </footer>
  );
}

export default SiteFooter;
