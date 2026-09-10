import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import {
  getMyEnrollment,
  getMyGlossary,
  getMyPlayLesson,
  getMyReadLesson,
  gradeMyReview,
  putMyProgress,
  searchMyCourse,
} from "../../api/my";
import Player from "../../components/Player/Player.jsx";
import Reader from "../../components/Reader/Reader.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./MyLesson.module.css";

/**
 * One lesson behind the enrollment, in whichever medium it is.
 *
 * A video lesson mounts the 006 player; a text lesson (023) mounts the
 * reader. Both take the pinned package version, persist review answers as
 * the 5.01.2 engagement record, and never receive the answer key. Which
 * one to mount is decided by the lesson's `kind` on the enrollment
 * detail, never by trying one route and catching the other's refusal —
 * 023b: that fallback keyed on a 404 the play route did not give.
 */
function MyLesson() {
  usePageTitle("Lesson");
  const { enrollmentId, packageId } = useParams();
  const [lesson, setLesson] = useState(null);
  const [medium, setMedium] = useState(null);
  const [error, setError] = useState(null);

  const fetchLesson = useCallback(
    (kind) =>
      kind === "text"
        ? getMyReadLesson(enrollmentId, packageId)
        : getMyPlayLesson(enrollmentId, packageId),
    [enrollmentId, packageId]
  );

  const reload = useCallback(
    () => fetchLesson(medium).then(setLesson),
    [fetchLesson, medium]
  );

  useEffect(() => {
    let cancelled = false;
    setLesson(null);
    setMedium(null);
    setError(null);
    getMyEnrollment(enrollmentId)
      .then((enrollment) => {
        const entry = enrollment.lessons.find(
          (item) => String(item.package_id) === packageId
        );
        if (!entry) throw new ApiError(404, null);
        return fetchLesson(entry.kind).then((data) => {
          if (cancelled) return;
          setLesson(data);
          setMedium(entry.kind === "text" ? "text" : "video");
        });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404)
          setError("This lesson is not part of your enrollment.");
        else setError("The lesson could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [enrollmentId, packageId, fetchLesson]);

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link> /{" "}
        <Link to={`/my/courses/${enrollmentId}`}>course</Link> / lesson
      </p>
      {error && <div className={styles.errorPanel}>{error}</div>}
      {lesson && medium === "video" && (
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
      {lesson && medium === "text" && (
        <>
          <h1 className={styles.lessonTitle}>{lesson.title}</h1>
          <Reader
            lesson={lesson}
            gradeAnswer={(questionKey, choiceKey) =>
              gradeMyReview(enrollmentId, packageId, questionKey, choiceKey)
            }
            onSearch={(query) => searchMyCourse(enrollmentId, query)}
            onLookup={(term) => getMyGlossary(enrollmentId, term)}
            // Answering is what opens the next section, and only the
            // server decides that — so a graded answer refetches rather
            // than unlocking anything locally.
            onAnswered={() => reload().catch(() => {})}
          />
        </>
      )}
    </main>
  );
}

export default MyLesson;
