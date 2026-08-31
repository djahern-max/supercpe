import { NavLink, useNavigate } from "react-router-dom";
import { useSession } from "../auth/SessionContext.jsx";
import styles from "./AdminNav.module.css";

function AdminNav() {
  const navigate = useNavigate();
  const { account, signOut } = useSession();

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <nav className={styles.nav}>
      <NavLink
        to="/admin/courses"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Courses
      </NavLink>
      <NavLink
        to="/admin/packages"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Packages
      </NavLink>
      <NavLink
        to="/admin/payments"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Payments
      </NavLink>
      <NavLink
        to="/admin/smes"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Experts
      </NavLink>
      <NavLink
        to="/admin/sponsor"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Sponsor
      </NavLink>
      <NavLink
        to="/admin/accounts"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Accounts
      </NavLink>
      <NavLink
        to="/admin/jurisdictions"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Jurisdictions
      </NavLink>
      <NavLink
        to="/admin/waiting-list"
        className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
      >
        Waiting list
      </NavLink>
      <span className={styles.spacer} />
      {account && <span className={styles.who}>{account.email}</span>}
      <button className={styles.signOut} type="button" onClick={handleSignOut}>
        Sign out
      </button>
    </nav>
  );
}

export default AdminNav;
