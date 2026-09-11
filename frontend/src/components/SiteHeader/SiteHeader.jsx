import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { roleHome } from "../../auth/RequireRole.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { SITE_FACE, useSiteFace } from "../../site/SiteContext.jsx";
import styles from "./SiteHeader.module.css";

const linkClass = ({ isActive }) => (isActive ? styles.linkActive : styles.link);

/**
 * The site's chrome: wordmark, the links that belong to the viewer's
 * role, the signed-in email, and Sign out. It states no course fact and
 * nothing about the Registry, and it decides nothing — SiteGate and
 * RequireRole own gating. It renders nothing:
 *
 *  1. until both the session and the site read have answered;
 *  2. while the site's face is coming-soon (`siteFace`, shared with
 *     SiteGate so the two cannot drift — 8.01, see that helper);
 *  3. under /admin, where AdminNav owns the chrome;
 *  4. on /change-password — an account forced through a password change
 *     is offered no way around it (RequireRole would only bounce it back).
 */
function SiteHeader() {
  const { account, signOut } = useSession();
  const face = useSiteFace();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  if (face !== SITE_FACE.OPEN) return null;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return null;
  if (pathname === "/change-password") return null;

  const handleSignOut = async () => {
    await signOut();
    // The public face of the site, not /login: while coming_soon that
    // is the landing page, which is correct. (signOut clears the session
    // in a transition so this navigate and the cleared session commit
    // together — see SessionContext.)
    navigate("/");
  };

  return (
    <header className={styles.header}>
      <Link className={styles.wordmark} to={account ? roleHome(account.role) : "/"}>
        super<span className={styles.accent}>CPE</span>
      </Link>
      <nav className={styles.nav} aria-label="Site">
        {!account && (
          <>
            <NavLink to="/courses" className={linkClass}>
              Courses
            </NavLink>
            <NavLink to="/how-it-works" className={linkClass}>
              How it works
            </NavLink>
            <NavLink to="/login" className={linkClass}>
              Sign in
            </NavLink>
            <NavLink to="/register" className={linkClass}>
              Create account
            </NavLink>
          </>
        )}
        {account?.role === "participant" && (
          <>
            <NavLink to="/my/courses" className={linkClass}>
              My courses
            </NavLink>
            <NavLink to="/courses" className={linkClass}>
              Courses
            </NavLink>
            <NavLink to="/account" className={linkClass}>
              Account
            </NavLink>
          </>
        )}
        {/* admin is unreachable here (null under /admin); if that rule
            ever changes it gets the reviewer row rather than a crash. */}
        {(account?.role === "reviewer" || account?.role === "admin") && (
          <NavLink to="/review" className={linkClass}>
            Review
          </NavLink>
        )}
        {account && (
          <>
            <span className={styles.who}>{account.email}</span>
            <button
              className={styles.signOut}
              type="button"
              onClick={handleSignOut}
            >
              Sign out
            </button>
          </>
        )}
      </nav>
    </header>
  );
}

export default SiteHeader;
