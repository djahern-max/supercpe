import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { register } from "../../api/register";
import { roleHome } from "../../auth/RequireRole.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import GoogleSignIn from "../../components/GoogleSignIn/GoogleSignIn.jsx";
import { US_JURISDICTIONS } from "../../constants/jurisdictions";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./Register.module.css";

/**
 * 017: self-registration. The success state shows the server's one
 * constant message verbatim — the page never says whether the address
 * was new. The form links the published registration policy (8.01.1);
 * it does not restate it.
 *
 * 030: "or sign up with Google" below the form. Same endpoint as the
 * sign-in page's button — creation is that endpoint's third branch — so
 * a Google account that already has a superCPE account simply signs in.
 */
function Register() {
  usePageTitle("Register");
  const navigate = useNavigate();
  const { setAccount } = useSession();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    state: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [errors, setErrors] = useState(null);

  const set = (field) => (event) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setErrors(null);
    try {
      const response = await register(form);
      setMessage(response.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The request failed. Please try again."]);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>
        super<span className={styles.accent}>CPE</span>
      </h1>
      <h2 className={styles.heading}>Create your account</h2>
      {message ? (
        <p className={styles.success}>{message}</p>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.label} htmlFor="register-name">
            Name
          </label>
          <input
            id="register-name"
            className={styles.input}
            value={form.name}
            onChange={set("name")}
            autoComplete="name"
          />
          <label className={styles.label} htmlFor="register-email">
            Email
          </label>
          <input
            id="register-email"
            className={styles.input}
            type="email"
            value={form.email}
            onChange={set("email")}
            autoComplete="email"
          />
          <label className={styles.label} htmlFor="register-password">
            Password
          </label>
          <input
            id="register-password"
            className={styles.input}
            type="password"
            value={form.password}
            onChange={set("password")}
            autoComplete="new-password"
          />
          <label className={styles.label} htmlFor="register-state">
            State of licensure (optional)
          </label>
          <select
            id="register-state"
            className={styles.input}
            value={form.state}
            onChange={set("state")}
          >
            <option value="">Choose…</option>
            {Object.entries(US_JURISDICTIONS).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
          {errors && (
            <ul className={styles.errorList}>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
          <button
            className={styles.button}
            type="submit"
            disabled={
              submitting ||
              !form.name.trim() ||
              !form.email.trim() ||
              !form.password
            }
          >
            {submitting ? "Creating…" : "Create account"}
          </button>
          <p className={styles.policyNote}>
            Registering means agreeing to the{" "}
            <Link to="/policies">registration and attendance policy</Link>.
          </p>
        </form>
      )}
      {!message && (
        <GoogleSignIn
          text="signup_with"
          onSuccess={(account) => {
            setAccount(account);
            navigate(roleHome(account.role), { replace: true });
          }}
        />
      )}
      <p className={styles.footerLink}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </main>
  );
}

export default Register;
