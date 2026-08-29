import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "./SessionContext.jsx";

export function roleHome(role) {
  if (role === "admin") return "/admin/courses";
  if (role === "reviewer") return "/review";
  return "/courses";
}

/**
 * Route wrapper: redirects to /login without a session, to /change-password
 * while the account's password change is forced, and to the account's home
 * when its role is not among `roles`.
 */
function RequireRole({ roles, children }) {
  const { account, loading } = useSession();
  const location = useLocation();

  if (loading) return null;
  if (!account) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (account.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  if (!roles.includes(account.role)) {
    return <Navigate to={roleHome(account.role)} replace />;
  }
  return children;
}

export default RequireRole;
