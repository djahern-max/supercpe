import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import {
  getAssessment,
  getAssessmentAttempt,
  saveAssessmentAnswers,
  startAssessmentAttempt,
  submitAssessmentAttempt,
} from "../../api/admin";
import Assessment from "../../components/Assessment/Assessment.jsx";
import styles from "./AdminAssessmentPreview.module.css";

/**
 * The preview mount for the qualified assessment, for admins and
 * reviewers. Unlike the player preview, attempts ARE recorded here (in
 * preview form, keyed to this browser session): 6.01.2 grading only means
 * anything against a stored attempt, and the admin attempts view shows
 * them.
 */
function AdminAssessmentPreview() {
  const { code } = useParams();
  const { account } = useSession();

  const api = useMemo(
    () => ({
      getAssessment: () => getAssessment(code),
      start: () => startAssessmentAttempt(code),
      saveAnswers: (attemptId, answers) =>
        saveAssessmentAnswers(code, attemptId, answers),
      submit: (attemptId, answers) =>
        submitAssessmentAttempt(code, attemptId, answers),
      getAttempt: (attemptId) => getAssessmentAttempt(code, attemptId),
    }),
    [code]
  );

  const isAdmin = account?.role === "admin";

  return (
    <main className={styles.page}>
      {isAdmin && <AdminNav />}
      <div className={styles.banner}>
        Preview — attempts are recorded as preview attempts, not completions.
      </div>
      <p className={styles.breadcrumb}>
        {isAdmin ? (
          <>
            <Link to="/admin/courses">Courses</Link> /{" "}
            <Link to={`/admin/courses/${code}`}>{code}</Link>
          </>
        ) : (
          <>
            <Link to="/review">Review</Link> /{" "}
            <Link to={`/review/courses/${code}`}>{code}</Link>
          </>
        )}{" "}
        / <Link to={`/admin/courses/${code}/preview`}>preview</Link> /
        assessment
      </p>
      <Assessment api={api} />
    </main>
  );
}

export default AdminAssessmentPreview;
