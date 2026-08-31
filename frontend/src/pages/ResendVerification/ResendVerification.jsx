import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { resendVerification } from "../../api/register";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./ResendVerification.module.css";

/**
 * 017: the general "didn't get your verification email?" affordance,
 * linked from the login page for everyone — a failed unverified login
 * looks exactly like a wrong password, so nothing may single anyone
 * out. The response is the same constant message as registration.
 */
function ResendVerification() {
  usePageTitle("Resend verification");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState(null);
  const [errors, setErrors] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setErrors(null);
    try {
      const response = await resendVerification(email);
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
      <h2 className={styles.heading}>Resend verification email</h2>
      {message ? (
        <p className={styles.success}>{message}</p>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.label} htmlFor="resend-email">
            Email
          </label>
          <input
            id="resend-email"
            className={styles.input}
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
          />
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
            disabled={submitting || !email.trim()}
          >
            {submitting ? "Sending…" : "Send it again"}
          </button>
        </form>
      )}
      <p className={styles.footerLink}>
        <Link to="/login">Back to sign in</Link>
      </p>
    </main>
  );
}

export default ResendVerification;
