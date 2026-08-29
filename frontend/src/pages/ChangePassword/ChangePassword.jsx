import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { changePassword } from "../../api/auth";
import { ApiError } from "../../api/client";
import { roleHome } from "../../auth/RequireRole.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./ChangePassword.module.css";

function ChangePassword() {
  const navigate = useNavigate();
  const { account, loading, setAccount } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [errors, setErrors] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) return null;
  if (!account) return <Navigate to="/login" replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (next !== repeat) {
      setErrors(["The new passwords do not match."]);
      return;
    }
    setSubmitting(true);
    setErrors(null);
    try {
      const updated = await changePassword(current, next);
      setAccount(updated);
      navigate(roleHome(updated.role), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The change failed. Try again."]);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>Change password</h1>
      {account.must_change_password && (
        <p className={styles.muted}>
          Choose your own password before continuing; the one you signed in
          with was issued for first login only.
        </p>
      )}
      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.label} htmlFor="current-password">
          Current password
        </label>
        <input
          id="current-password"
          className={styles.input}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <label className={styles.label} htmlFor="new-password">
          New password (at least 12 characters)
        </label>
        <input
          id="new-password"
          className={styles.input}
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
        <label className={styles.label} htmlFor="repeat-password">
          Repeat new password
        </label>
        <input
          id="repeat-password"
          className={styles.input}
          type="password"
          autoComplete="new-password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
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
          disabled={!current || !next || !repeat || submitting}
        >
          {submitting ? "Changing…" : "Change password"}
        </button>
        <p className={styles.muted}>
          Your other sessions are signed out when the password changes.
        </p>
      </form>
    </main>
  );
}

export default ChangePassword;
