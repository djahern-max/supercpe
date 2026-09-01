import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import {
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
 * one to mount is not guessed from the payload's shape — the course
 * detail already says each lesson's `kind`, and the two endpoints refuse
 * each other's lessons with 404, so this tries the play route first and
 * falls back to the reader.
 */
function MyLesson() {
  usePageTitle("Lesson");
  const { enrollmentId, packageId } = useParams();
  const [lesson, setLesson] = useState(null);
  const [medium, setMedium] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    return getMyPlayLesson(enrollmentId, packageId)
      .then((data) => {
        setLesson(data);
        setMedium("video");
      })
      .catch((err) => {
        if (!(err instanceof ApiError) || err.status !== 404) throw err;
        return getMyReadLesson(enrollmentId, packageId).then((data) => {
          setLesson(data);
          setMedium("text");
        });
      });
  }, [enrollmentId, packageId]);

  useEffect(() => {
    setLesson(null);
    setMedium(null);
    setError(null);
    load().catch((err) => {
      if (err instanceof ApiError && err.status === 404)
        setError("This lesson is not part of your enrollment.");
      else setError("The lesson could not be loaded.");
    });
  }, [load]);

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
            onAnswered={() => load().catch(() => {})}
          />
        </>
      )}
    </main>
  );
}

export default MyLesson;
