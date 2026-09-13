import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { login } from "../../api/auth";
import { roleHome } from "../../auth/RequireRole.jsx";
import GoogleSignIn from "../../components/GoogleSignIn/GoogleSignIn.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import { SITE_FACE, useSiteFace } from "../../site/SiteContext.jsx";
import styles from "./Login.module.css";

/**
 * Not linked from the coming-soon landing page: while the site is
 * coming_soon, staff and testers know this address (the 025 header links
 * it once the site is open). One error line for every failure — the
 * server does not say which part was wrong, and neither do we.
 *
 * 027: a Create account link below the form, under the same `siteFace()`
 * decision as the header — at open, or with a session — so the
 * coming-soon landing page still advertises nothing.
 *
 * 030: Google's button below the form under the same decision, and only
 * when the server reports a client id; a successful Google sign-in
 * finishes exactly as a password sign-in does (`finishSignIn`).
 */
function Login() {
  usePageTitle("Sign in");
  const navigate = useNavigate();
  const location = useLocation();
  const { setAccount } = useSession();
  const face = useSiteFace();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const finishSignIn = (account) => {
    setAccount(account);
    if (account.must_change_password) {
      navigate("/change-password", { replace: true });
    } else {
      navigate(location.state?.from ?? roleHome(account.role), {
        replace: true,
      });
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setFailed(false);
    try {
      finishSignIn(await login(email.trim(), password));
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
      <GoogleSignIn onSuccess={finishSignIn} />
      {face === SITE_FACE.OPEN && (
        <p className={styles.registerLink}>
          New here? <Link to="/register">Create account</Link>
        </p>
      )}
    </main>
  );
}

export default Login;
