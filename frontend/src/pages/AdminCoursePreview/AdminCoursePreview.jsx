import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import {
  getCourseGlossary,
  getPlayLesson,
  getReadLesson,
  gradeReview,
  searchCourse,
} from "../../api/admin";
import { getReviewCourse } from "../../api/review";
import Player from "../../components/Player/Player.jsx";
import Reader from "../../components/Reader/Reader.jsx";
import styles from "./AdminCoursePreview.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * The preview mount for the participant player, for admins and reviewers
 * (a reviewer must see the program they sign off on, 4.02). 010 mounts the
 * same Player for enrolled participants and adds persistence; nothing a
 * previewer does here is recorded anywhere.
 */
function AdminCoursePreview() {
  const { code, packageId } = useParams();
  const { account, refresh: refreshSession } = useSession();
  const [course, setCourse] = useState(null);
  const [lesson, setLesson] = useState(null);
  const [medium, setMedium] = useState(null);
  const [error, setError] = useState(null);

  const handleAuthFailure = useCallback(() => {
    refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    setError(null);
    setLesson(null);
    setMedium(null);
    if (packageId) {
      // A video lesson plays, a text lesson reads; each route 404s the
      // other's lessons, so try the player and fall back to the reader.
      getPlayLesson(code, packageId)
        .then((data) => {
          setLesson(data);
          setMedium("video");
        })
        .catch((err) => {
          if (!(err instanceof ApiError) || err.status !== 404) throw err;
          return getReadLesson(code, packageId).then((data) => {
            setLesson(data);
            setMedium("text");
          });
        })
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) handleAuthFailure();
          else if (err instanceof ApiError && err.status === 404)
            setError("This lesson is not attached to the course.");
          else setError("Could not load the lesson. Is the backend running?");
        });
    } else {
      getReviewCourse(code)
        .then(setCourse)
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) handleAuthFailure();
          else if (err instanceof ApiError && err.status === 404)
            setError("There is no course with this code.");
          else setError("Could not load the course. Is the backend running?");
        });
    }
  }, [code, packageId, handleAuthFailure]);

  const isAdmin = account?.role === "admin";

  return (
    <main className={styles.page}>
      {isAdmin && <AdminNav />}
      <div className={styles.banner}>Preview — nothing is recorded.</div>
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
        /{" "}
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
                    {item.kind === "text"
                      ? `Study guide · ${item.word_count.toLocaleString()} words counted`
                      : formatDuration(item.duration_seconds)}
                  </span>
                </Link>
              </li>
            ))}
            <li>
              <Link
                className={styles.lessonLink}
                to={`/admin/courses/${code}/preview/assessment`}
              >
                <span className={styles.lessonPosition}>✓</span>
                <span>Qualified assessment</span>
              </Link>
            </li>
          </ul>
        </section>
      )}

      {packageId && lesson && medium === "video" && (
        <Player
          lesson={lesson}
          gradeAnswer={(questionKey, choiceKey) =>
            gradeReview(code, packageId, questionKey, choiceKey)
          }
        />
      )}
      {packageId && lesson && medium === "text" && (
        <Reader
          lesson={lesson}
          gradeAnswer={(questionKey, choiceKey) =>
            gradeReview(code, packageId, questionKey, choiceKey)
          }
          onSearch={(query) => searchCourse(code, query)}
          onLookup={(term) => getCourseGlossary(code, term)}
        />
      )}
    </main>
  );
}

export default AdminCoursePreview;
