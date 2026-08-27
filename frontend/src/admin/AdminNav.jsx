import { NavLink } from "react-router-dom";
import styles from "./AdminNav.module.css";

function AdminNav() {
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
    </nav>
  );
}

export default AdminNav;
