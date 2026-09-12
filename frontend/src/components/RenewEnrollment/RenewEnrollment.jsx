import { useState } from "react";
import { ApiError } from "../../api/client";
import { renewCourse } from "../../api/courses";
import styles from "./RenewEnrollment.module.css";

/**
 * 028: the one button for an expired enrollment the participant may renew
 * — shared by the course page, the /my/courses card, and the enrollment
 * page so the three cannot disagree on the words. The server decides
 * eligibility (a paid purchase, nothing active or completed, the most
 * recent enrollment expired); this renders only when the payload's
 * `renewable` says so, and shows the 422 lines verbatim otherwise.
 * `onRenewed` receives the new enrollment card.
 */
function RenewEnrollment({ courseCode, onRenewed, className }) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState(null);

  const handleRenew = async () => {
    setErrors(null);
    setBusy(true);
    try {
      const enrollment = await renewCourse(courseCode);
      setBusy(false);
      onRenewed(enrollment);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The enrollment could not be started. Try again in a moment."]);
      }
    }
  };

  return (
    <div className={styles.wrap}>
      <button
        className={className ?? styles.button}
        type="button"
        disabled={busy}
        onClick={handleRenew}
      >
        {busy ? "Starting…" : "Start a new enrollment (no charge)"}
      </button>
      <p className={styles.note}>
        You purchased this course; a new one-year enrollment costs nothing.
      </p>
      {errors && (
        <ul className={styles.errorList}>
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default RenewEnrollment;
