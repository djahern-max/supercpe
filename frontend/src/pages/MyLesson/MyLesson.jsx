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
import { deriveNextStep, reviewRemaining } from "./nextStep.js";

/**
 * One lesson behind the enrollment, in whichever medium it is.
 *
 * A video lesson mounts the 006 player; a text lesson (023) mounts the
 * reader. Both take the pinned package version, persist review answers as
 * the 5.01.2 engagement record, and never receive the answer key. Which
 * one to mount is decided by the lesson's `kind` on the enrollment
 * detail, never by trying one route and catching the other's refusal —
 * 023b: that fallback keyed on a 404 the play route did not give.
 *
 * 027: the enrollment detail is kept and refetched after every graded
 * answer, so both surfaces can say what comes next (`deriveNextStep`) —
 * the next unread lesson, the assessment once it is available, or the
 * course page — from fields the payload already carries.
 */
function MyLesson() {
  usePageTitle("Lesson");
  const { enrollmentId, packageId } = useParams();
  const [lesson, setLesson] = useState(null);
  const [enrollment, setEnrollment] = useState(null);
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

  const reloadEnrollment = useCallback(
    () => getMyEnrollment(enrollmentId).then(setEnrollment),
    [enrollmentId]
  );

  useEffect(() => {
    let cancelled = false;
    setLesson(null);
    setEnrollment(null);
    setMedium(null);
    setError(null);
    getMyEnrollment(enrollmentId)
      .then((detail) => {
        const entry = detail.lessons.find(
          (item) => String(item.package_id) === packageId
        );
        if (!entry) throw new ApiError(404, null);
        return fetchLesson(entry.kind).then((data) => {
          if (cancelled) return;
          setEnrollment(detail);
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

  // Grading persists the answer (5.01.2 record); the enrollment detail is
  // then refetched so `done`, `assessment_available`, and the sitting
  // counts the next-step derivation reads are the server's, not guessed.
  const gradeAnswer = (questionKey, choiceKey) =>
    gradeMyReview(enrollmentId, packageId, questionKey, choiceKey).then(
      (result) => {
        reloadEnrollment().catch(() => {});
        return result;
      }
    );

  const nextStep = enrollment ? deriveNextStep(enrollment, packageId) : null;

  // 037: the breadcrumb used to read "My courses / course / lesson". The
  // real names were never unavailable — the enrollment detail carries the
  // course title and every lesson's position and title, for a video
  // lesson as much as a text one, and the reader payload now says the
  // same thing about itself. Neither is read out of the URL.
  const entry = enrollment?.lessons.find(
    (item) => String(item.package_id) === packageId
  );
  const courseTitle = lesson?.course_title ?? enrollment?.title ?? null;
  const lessonPosition = lesson?.lesson_position ?? entry?.position ?? null;
  const lessonTitle = lesson?.title ?? entry?.title ?? null;

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link>
        {courseTitle && (
          <>
            {" / "}
            <Link to={`/my/courses/${enrollmentId}`}>{courseTitle}</Link>
          </>
        )}
        {lessonTitle && (
          <>
            {" / "}
            {lessonPosition ? `Lesson ${lessonPosition}: ` : ""}
            {lessonTitle}
          </>
        )}
      </p>
      {error && <div className={styles.errorPanel}>{error}</div>}
      {lesson && medium === "video" && (
        <Player
          lesson={lesson}
          initialFurthestSeconds={lesson.furthest_seconds}
          gradeAnswer={gradeAnswer}
          onProgress={(seconds) =>
            // Fire and forget: a lost report only costs the throttle
            // window, and the server never lowers the stored point.
            putMyProgress(enrollmentId, packageId, seconds).catch(() => {})
          }
          nextStep={nextStep}
          reviewRemaining={
            enrollment ? reviewRemaining(enrollment, packageId) : 0
          }
        />
      )}
      {lesson && medium === "text" && (
        <>
          <h1 className={styles.lessonTitle}>{lesson.title}</h1>
          <Reader
            lesson={lesson}
            gradeAnswer={gradeAnswer}
            onSearch={(query) => searchMyCourse(enrollmentId, query)}
            onLookup={(term) => getMyGlossary(enrollmentId, term)}
            // Answering is what opens the next section, and only the
            // server decides that — so a graded answer refetches rather
            // than unlocking anything locally.
            onAnswered={() => reload().catch(() => {})}
            // Continue asks once more, so it shows what the server
            // unlocked even if the post-answer refetch is still in flight.
            onContinue={() => reload().catch(() => {})}
            nextStep={nextStep}
          />
        </>
      )}
    </main>
  );
}

export default MyLesson;
