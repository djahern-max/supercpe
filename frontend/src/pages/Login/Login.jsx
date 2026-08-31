import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { login } from "../../api/auth";
import { roleHome } from "../../auth/RequireRole.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./Login.module.css";

/**
 * Deliberately not linked from any page: while the site is coming_soon,
 * staff and testers know this address. One error line for every failure —
 * the server does not say which part was wrong, and neither do we.
 */
function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setAccount } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setFailed(false);
    try {
      const account = await login(email.trim(), password);
      setAccount(account);
      if (account.must_change_password) {
        navigate("/change-password", { replace: true });
      } else {
        navigate(location.state?.from ?? roleHome(account.role), {
          replace: true,
        });
      }
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>
        super<span className={styles.accent}>CPE</span>
      </h1>
      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.label} htmlFor="login-email">
          Email
        </label>
        <input
          id="login-email"
          className={styles.input}
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label className={styles.label} htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          className={styles.input}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {failed && (
          <p className={styles.error}>Email or password is incorrect.</p>
        )}
        <button
          className={styles.button}
          type="submit"
          disabled={!email.trim() || !password || submitting}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        {/* 017: a general affordance for everyone — an unverified login
            failure looks exactly like a wrong password, so this link may
            not single anyone out. */}
        <p className={styles.resendLink}>
          <Link to="/resend-verification">
            Didn't get your verification email?
          </Link>
        </p>
      </form>
    </main>
  );
}

export default Login;
