import { useState } from "react";
import { ApiError } from "../../api/client";
import { enrollWithSubscription } from "../../api/subscribe";
import styles from "../RenewEnrollment/RenewEnrollment.module.css";

/**
 * 029: the one button for a current subscriber's enrollment — shared by
 * the course page and the /my/courses card so the two cannot disagree on
 * the words. The server decides (a current subscription, a published
 * course, nothing active or completed); this renders only where the
 * payload says so, and shows the 422 lines verbatim otherwise.
 * `onEnrolled` receives the new enrollment card. `again` switches the
 * label for an expired course being started over.
 */
function SubscriptionEnroll({ courseCode, onEnrolled, className, again = false }) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState(null);

  const handleEnroll = async () => {
    setErrors(null);
    setBusy(true);
    try {
      const enrollment = await enrollWithSubscription(courseCode);
      setBusy(false);
      onEnrolled(enrollment);
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
        onClick={handleEnroll}
      >
        {busy
          ? "Starting…"
          : again
            ? "Enroll again (included in your subscription)"
            : "Enroll (included in your subscription)"}
      </button>
      <p className={styles.note}>
        Your subscription covers this course; a new one-year enrollment
        starts now.
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

export default SubscriptionEnroll;
