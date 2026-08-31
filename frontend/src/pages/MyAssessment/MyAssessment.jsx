import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getMyAssessment,
  getMyAttempt,
  myCertificateUrl,
  saveMyAnswers,
  startMyAttempt,
  submitMyAttempt,
} from "../../api/my";
import Assessment from "../../components/Assessment/Assessment.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./MyAssessment.module.css";

/**
 * The qualified assessment behind the enrollment, reusing 007's component
 * with the enrollment endpoints. When the assessment is not available the
 * reasons are shown instead of the form; the server enforces the same
 * rules on start either way.
 */
function MyAssessment() {
  usePageTitle("Assessment");
  const { enrollmentId } = useParams();
  const [gate, setGate] = useState(null);

  const api = useMemo(
    () => ({
      getAssessment: () => getMyAssessment(enrollmentId),
      start: () => startMyAttempt(enrollmentId),
      saveAnswers: (attemptId, answers) =>
        saveMyAnswers(enrollmentId, attemptId, answers),
      submit: (attemptId, answers) =>
        submitMyAttempt(enrollmentId, attemptId, answers),
      getAttempt: (attemptId) => getMyAttempt(enrollmentId, attemptId),
    }),
    [enrollmentId]
  );

  useEffect(() => {
    getMyAssessment(enrollmentId)
      .then(setGate)
      .catch(() => setGate({ available: true, unavailable_reasons: [] }));
  }, [enrollmentId]);

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link> /{" "}
        <Link to={`/my/courses/${enrollmentId}`}>course</Link> / assessment
      </p>
      {gate !== null &&
      !gate.available &&
      !gate.open_attempt_id &&
      gate.unavailable_reasons?.length > 0 ? (
        <section className={styles.reasonPanel}>
          <p className={styles.reasonTitle}>
            The assessment is not available yet:
          </p>
          <ul className={styles.reasonList}>
            {gate.unavailable_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      ) : (
        gate !== null && (
          <Assessment api={api} certificateUrl={myCertificateUrl} />
        )
      )}
    </main>
  );
}

export default MyAssessment;
