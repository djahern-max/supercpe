import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import mark from "../assets/brand/mark.png";
import { useSession } from "../auth/SessionContext.jsx";
import useMediaQuery from "../hooks/useMediaQuery.js";
import styles from "./AdminNav.module.css";

const LINKS = [
  ["/admin/courses", "Courses"],
  ["/admin/packages", "Packages"],
  ["/admin/payments", "Payments"],
  ["/admin/subscriptions", "Subscriptions"],
  ["/admin/smes", "Experts"],
  ["/admin/sponsor", "Sponsor"],
  ["/admin/accounts", "Accounts"],
  ["/admin/jurisdictions", "Jurisdictions"],
  ["/admin/waiting-list", "Waiting list"],
];

// 033: the width at and below which the row collapses behind a menu
// button. The same number is in AdminNav.module.css.
const NARROW = "(max-width: 720px)";
const MENU_ID = "admin-nav-menu";

const linkClass = ({ isActive }) => (isActive ? styles.linkActive : styles.link);

/**
 * The admin chrome, rendered by every /admin page. Above 720px it is one
 * wrapping row: the mark, the nine links, the signed-in email, Sign out.
 * At and below 720px (033) the row is the mark, a menu button, and Sign
 * out; the button opens a vertical list of the same links and the email.
 * Sign out is reachable in both states and navigates to /login (025).
 */
function AdminNav() {
  const navigate = useNavigate();
  const { account, signOut } = useSession();
  const narrow = useMediaQuery(NARROW);
  const [open, setOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  const links = LINKS.map(([to, label]) => (
    <NavLink key={to} to={to} className={linkClass}>
      {label}
    </NavLink>
  ));
  const who = account && <span className={styles.who}>{account.email}</span>;

  return (
    <nav className={styles.nav} aria-label="Admin">
      <div className={styles.row}>
        <Link className={styles.brand} to="/admin/courses">
          <img className={styles.mark} src={mark} alt="" />
          <span className={styles.title}>Admin</span>
        </Link>
        {narrow ? (
          <button
            className={styles.menuButton}
            type="button"
            aria-expanded={open}
            aria-controls={MENU_ID}
            onClick={() => setOpen((current) => !current)}
          >
            Menu
          </button>
        ) : (
          <div className={styles.links}>
            {links}
            <span className={styles.spacer} />
            {who}
          </div>
        )}
        <button className={styles.signOut} type="button" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
      {narrow && (
        <div id={MENU_ID} className={styles.menu} hidden={!open}>
          {links}
          {who}
        </div>
      )}
    </nav>
  );
}

export default AdminNav;
