import ComingSoon from "../../pages/ComingSoon/ComingSoon.jsx";
import { SITE_FACE, useSiteFace } from "../../site/SiteContext.jsx";

/**
 * Wraps the public pages, and the catch-all route. While site_mode is
 * coming_soon and nobody is signed in, every gated path renders the 015
 * landing page instead of its content — deliberately with no link to
 * /login and never a word about the Registry (the page reads only
 * /api/v1/site and /api/v1/landing).
 */
function SiteGate({ children }) {
  const face = useSiteFace();

  // On a failed /site read, `siteFace` answers OPEN and we fall through
  // to the page; it reports backend trouble in its own words.
  if (face === SITE_FACE.LOADING) return null;
  if (face === SITE_FACE.OPEN) return children;

  return <ComingSoon />;
}

export default SiteGate;
