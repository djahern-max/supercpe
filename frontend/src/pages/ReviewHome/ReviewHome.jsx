import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listReviewCourses } from "../../api/review";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./ReviewHome.module.css";

const STANDING_LABELS = {
  current: "review is current",
  superseded: "superseded by a content change",
  none: "no approved review",
};

export function ReviewHeader() {
  const navigate = useNavigate();
  const { account, signOut } = useSession();
  return (
    <header className={styles.header}>
      <Link className={styles.home} to="/review">
        superCPE <span className={styles.headerRole}>review</span>
      </Link>
      <span className={styles.spacer} />
      {account && <span className={styles.who}>{account.email}</span>}
      <button
        className={styles.signOut}
        type="button"
        onClick={async () => {
          await signOut();
          navigate("/login");
        }}
      >
        Sign out
      </button>
    </header>
  );
}

/**
 * The reviewer's home: every course with its current-review standing
 * (4.02). Reviewers see nothing under /admin; recording a review is the
 * only write this surface has.
 */
function ReviewHome() {
  const navigate = useNavigate();
  const { refresh: refreshSession } = useSession();
  const [courses, setCourses] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listReviewCourses()
      .then(setCourses)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setError("Could not load courses. Is the backend running?");
      });
  }, [refreshSession]);

  return (
    <main className={styles.page}>
      <ReviewHeader />
      <h1 className={styles.heading}>Courses to review</h1>
      {error && <div className={styles.errorPanel}>{error}</div>}
      {!error && courses === null && (
        <p className={styles.muted}>Loading courses…</p>
      )}
      {courses !== null && courses.length === 0 && (
        <p className={styles.muted}>There are no courses yet.</p>
      )}
      {courses !== null && courses.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Title</th>
              <th>Status</th>
              <th>Review standing</th>
              <th>Last reviewed</th>
            </tr>
          </thead>
          <tbody>
            {courses.map((course) => (
              <tr
                key={course.course_code}
                className={styles.row}
                onClick={() =>
                  navigate(`/review/courses/${course.course_code}`)
                }
              >
                <td>{course.course_code}</td>
                <td>{course.title}</td>
                <td>{course.status}</td>
                <td>
                  {STANDING_LABELS[course.review_standing] ??
                    course.review_standing}
                </td>
                <td>{course.last_reviewed ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

export default ReviewHome;
