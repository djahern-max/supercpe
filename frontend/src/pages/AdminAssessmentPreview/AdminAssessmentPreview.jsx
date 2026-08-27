import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import TokenForm from "../../admin/TokenForm.jsx";
import { getToken, setToken } from "../../admin/token";
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
 * The admin preview mount for the qualified assessment. Unlike the player
 * preview, attempts ARE recorded here (in preview form, keyed to this
 * browser session): 6.01.2 grading only means anything against a stored
 * attempt, and the admin attempts view shows them.
 */
function AdminAssessmentPreview() {
  const { code } = useParams();
  const [token, setTokenState] = useState(getToken());

  const api = useMemo(
    () => ({
      getAssessment: () => getAssessment(code, token),
      start: () => startAssessmentAttempt(code, token),
      saveAnswers: (attemptId, answers) =>
        saveAssessmentAnswers(code, attemptId, answers, token),
      submit: (attemptId, answers) =>
        submitAssessmentAttempt(code, attemptId, answers, token),
      getAttempt: (attemptId) => getAssessmentAttempt(code, attemptId, token),
    }),
    [code, token]
  );

  if (!token) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Assessment preview {code}</h1>
        <TokenForm
          onSubmit={(value) => {
            setToken(value);
            setTokenState(value);
          }}
        />
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <AdminNav />
      <div className={styles.banner}>
        Preview — attempts are recorded as preview attempts, not completions.
      </div>
      <p className={styles.breadcrumb}>
        <Link to="/admin/courses">Courses</Link> /{" "}
        <Link to={`/admin/courses/${code}`}>{code}</Link> /{" "}
        <Link to={`/admin/courses/${code}/preview`}>preview</Link> / assessment
      </p>
      <Assessment api={api} />
    </main>
  );
}

export default AdminAssessmentPreview;
