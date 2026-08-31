import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import {
  getMyPlayLesson,
  gradeMyReview,
  putMyProgress,
} from "../../api/my";
import Player from "../../components/Player/Player.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./MyLesson.module.css";

/**
 * The 006 player mounted behind the enrollment: the lesson payload comes
 * from the pinned package version, review answers persist as the 5.01.2
 * engagement record, and the furthest point watched is reported back
 * (monotonic server-side).
 */
function MyLesson() {
  usePageTitle("Lesson");
  const { enrollmentId, packageId } = useParams();
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLesson(null);
    setError(null);
    getMyPlayLesson(enrollmentId, packageId)
      .then(setLesson)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404)
          setError("This lesson is not part of your enrollment.");
        else setError("The lesson could not be loaded.");
      });
  }, [enrollmentId, packageId]);

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link> /{" "}
        <Link to={`/my/courses/${enrollmentId}`}>course</Link> / lesson
      </p>
      {error && <div className={styles.errorPanel}>{error}</div>}
      {lesson && (
        <Player
          lesson={lesson}
          initialFurthestSeconds={lesson.furthest_seconds}
          gradeAnswer={(questionKey, choiceKey) =>
            gradeMyReview(enrollmentId, packageId, questionKey, choiceKey)
          }
          onProgress={(seconds) =>
            // Fire and forget: a lost report only costs the throttle
            // window, and the server never lowers the stored point.
            putMyProgress(enrollmentId, packageId, seconds).catch(() => {})
          }
        />
      )}
    </main>
  );
}

export default MyLesson;
