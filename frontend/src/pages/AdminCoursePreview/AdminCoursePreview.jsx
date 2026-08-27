import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import TokenForm from "../../admin/TokenForm.jsx";
import { clearToken, getToken, setToken } from "../../admin/token";
import { ApiError } from "../../api/client";
import { getCourse, getPlayLesson, gradeReview } from "../../api/admin";
import Player from "../../components/Player/Player.jsx";
import styles from "./AdminCoursePreview.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * The admin preview mount for the participant player. 010 mounts the same
 * Player for enrolled participants and adds persistence; nothing a
 * previewing admin does here is recorded anywhere.
 */
function AdminCoursePreview() {
  const { code, packageId } = useParams();
  const [token, setTokenState] = useState(getToken());
  const [course, setCourse] = useState(null);
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState(null);

  const handleAuthFailure = useCallback(() => {
    clearToken();
    setTokenState(null);
    setCourse(null);
    setLesson(null);
  }, []);

  useEffect(() => {
    if (!token) return;
    setError(null);
    setLesson(null);
    if (packageId) {
      getPlayLesson(code, packageId, token)
        .then(setLesson)
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) handleAuthFailure();
          else if (err instanceof ApiError && err.status === 404)
            setError("This lesson is not attached to the course.");
          else setError("Could not load the lesson. Is the backend running?");
        });
    } else {
      getCourse(code, token)
        .then(setCourse)
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) handleAuthFailure();
          else if (err instanceof ApiError && err.status === 404)
            setError("There is no course with this code.");
          else setError("Could not load the course. Is the backend running?");
        });
    }
  }, [token, code, packageId, handleAuthFailure]);

  if (!token) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Preview {code}</h1>
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
      <div className={styles.banner}>Preview — nothing is recorded.</div>
      <p className={styles.breadcrumb}>
        <Link to="/admin/courses">Courses</Link> /{" "}
        <Link to={`/admin/courses/${code}`}>{code}</Link> /{" "}
        {packageId ? (
          <Link to={`/admin/courses/${code}/preview`}>preview</Link>
        ) : (
          "preview"
        )}
      </p>

      {error && <div className={styles.errorPanel}>{error}</div>}

      {!packageId && course && (
        <section className={styles.card}>
          <h1 className={styles.heading}>{course.title}</h1>
          {course.lessons.length === 0 && (
            <p className={styles.muted}>No lessons attached yet.</p>
          )}
          <ul className={styles.lessonList}>
            {course.lessons.map((item) => (
              <li key={item.package_id}>
                <Link
                  className={styles.lessonLink}
                  to={`/admin/courses/${code}/preview/${item.package_id}`}
                >
                  <span className={styles.lessonPosition}>{item.position}.</span>
                  <span>{item.title}</span>
                  <span className={styles.muted}>
                    {formatDuration(item.duration_seconds)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {packageId && lesson && (
        <Player
          lesson={lesson}
          gradeAnswer={(questionKey, choiceKey) =>
            gradeReview(code, packageId, questionKey, choiceKey, token)
          }
        />
      )}
    </main>
  );
}

export default AdminCoursePreview;
