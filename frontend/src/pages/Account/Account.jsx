import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyState, setMyState } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import { US_JURISDICTIONS } from "../../constants/jurisdictions";
import styles from "./Account.module.css";

/**
 * 020: the participant's account page — today just their state of
 * licensure, which the course pages' "For your board" hint keys on.
 * Their claim about themselves, changeable and clearable at will.
 */
function Account() {
  const { account } = useSession();
  const [state, setState] = useState(null);
  const [status, setStatus] = useState("loading");
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMyState()
      .then((data) => {
        if (cancelled) return;
        setState(data.state ?? "");
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = async (event) => {
    const next = event.target.value;
    setState(next);
    setSaved(false);
    setErrors(null);
    try {
      const data = await setMyState(next);
      setState(data.state ?? "");
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The change could not be saved. Try again."]);
      }
    }
  };

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link>
      </p>
      <h1 className={styles.heading}>Account</h1>
      {account && <p className={styles.muted}>{account.email}</p>}

      <section className={styles.card}>
        <label className={styles.label} htmlFor="account-state">
          State of licensure
        </label>
        {status === "loading" && <p className={styles.muted}>Loading…</p>}
        {status === "error" && (
          <p className={styles.muted}>
            Your state could not be loaded. Reload to try again.
          </p>
        )}
        {status === "ok" && (
          <select
            id="account-state"
            className={styles.select}
            value={state}
            onChange={handleChange}
          >
            <option value="">Not set</option>
            {Object.entries(US_JURISDICTIONS).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        )}
        <p className={styles.muted}>
          Used to show what your board's rules mean for a course's
          recommended credit, when superCPE has verified them. Optional;
          it never appears on a certificate.
        </p>
        {saved && <p className={styles.saved}>Saved.</p>}
        {errors && (
          <ul className={styles.errorList}>
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
      </section>

      <p className={styles.muted}>
        <Link to="/change-password">Change your password</Link>
      </p>
    </main>
  );
}

export default Account;
