import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import TokenForm from "../../admin/TokenForm.jsx";
import { clearToken, getToken, setToken } from "../../admin/token";
import { ApiError } from "../../api/client";
import { listAttempts } from "../../api/admin";
import styles from "./AdminCourseAttempts.module.css";

function formatTimestamp(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

/**
 * Every attempt at the course's assessment, with per-answer detail. The
 * admin may see everything — including which answers a failed attempt got
 * wrong; the participant may not (6.01.2 sub-ii binds what is shown to the
 * test taker, not what the sponsor records).
 */
function AdminCourseAttempts() {
  const { code } = useParams();
  const [token, setTokenState] = useState(getToken());
  const [attempts, setAttempts] = useState(null);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);

  const handleAuthFailure = useCallback(() => {
    clearToken();
    setTokenState(null);
    setAttempts(null);
  }, []);

  useEffect(() => {
    if (!token) return;
    listAttempts(code, token)
      .then(setAttempts)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) handleAuthFailure();
        else if (err instanceof ApiError && err.status === 404)
          setError("There is no course with this code.");
        else setError("Could not load attempts. Is the backend running?");
      });
  }, [token, code, handleAuthFailure]);

  if (!token) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Attempts for {code}</h1>
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
      <p className={styles.breadcrumb}>
        <Link to="/admin/courses">Courses</Link> /{" "}
        <Link to={`/admin/courses/${code}`}>{code}</Link> / attempts
      </p>

      {error && <div className={styles.errorPanel}>{error}</div>}

      {attempts && attempts.length === 0 && (
        <p className={styles.muted}>No attempts yet.</p>
      )}

      {attempts && attempts.length > 0 && (
        <section className={styles.card}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>#</th>
                <th>Status</th>
                <th>Score</th>
                <th>Correct</th>
                <th>Started</th>
                <th>Submitted</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((attempt) => (
                <tr
                  key={attempt.id}
                  className={styles.row}
                  onClick={() =>
                    setOpenId(openId === attempt.id ? null : attempt.id)
                  }
                >
                  <td>
                    {attempt.id}
                    {attempt.is_preview && (
                      <span className={styles.previewBadge}>preview</span>
                    )}
                  </td>
                  <td>{attempt.status}</td>
                  <td>
                    {attempt.score_pct !== null
                      ? `${Number(attempt.score_pct)}%`
                      : "—"}
                  </td>
                  <td>
                    {attempt.correct_count !== null
                      ? `${attempt.correct_count} / ${attempt.question_count}`
                      : `— / ${attempt.question_count}`}
                  </td>
                  <td>{formatTimestamp(attempt.started_at)}</td>
                  <td>{formatTimestamp(attempt.submitted_at)}</td>
                  <td className={styles.muted}>
                    {openId === attempt.id ? "hide" : "detail"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {openId !== null &&
            attempts
              .filter((attempt) => attempt.id === openId)
              .map((attempt) => (
                <div key={attempt.id} className={styles.detail}>
                  <p className={styles.muted}>
                    Attempt {attempt.id} · passing threshold{" "}
                    {Number(attempt.passing_pct)}% · packages:{" "}
                    {attempt.package_versions
                      .map((p) => `#${p.package_id} v${p.version}`)
                      .join(", ")}
                  </p>
                  {attempt.answers.length === 0 && (
                    <p className={styles.muted}>No answers saved.</p>
                  )}
                  {attempt.answers.map((answer) => (
                    <p key={answer.question_id} className={styles.answerLine}>
                      <span className={styles.answerMeta}>
                        {answer.question_key}
                        {answer.is_correct === true && " · correct"}
                        {answer.is_correct === false && " · wrong"}
                        {answer.is_correct === null && " · ungraded"}
                      </span>
                      {answer.stem}
                      <span className={styles.answerChosen}>
                        answered: {answer.chosen_text}
                      </span>
                    </p>
                  ))}
                </div>
              ))}
        </section>
      )}
    </main>
  );
}

export default AdminCourseAttempts;
