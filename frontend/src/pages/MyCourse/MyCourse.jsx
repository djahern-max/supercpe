import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyEnrollment, myCertificateUrl } from "../../api/my";
import styles from "./MyCourse.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * One enrollment: the 004 course facts the participant enrolled on, the
 * lesson list with progress (each mounting the 006 player through the
 * enrollment endpoints), and the assessment link — enabled only when every
 * review question is answered, with the reasons spelled out otherwise.
 */
function MyCourse() {
  const { enrollmentId } = useParams();
  const [enrollment, setEnrollment] = useState(null);
  const [status, setStatus] = useState("loading");

  const load = useCallback(() => {
    getMyEnrollment(enrollmentId)
      .then((data) => {
        setEnrollment(data);
        setStatus("ok");
      })
      .catch((err) => {
        setStatus(
          err instanceof ApiError && err.status === 404 ? "notfound" : "error"
        );
      });
  }, [enrollmentId]);

  useEffect(() => {
    load();
  }, [load]);

  if (status === "loading") {
    return (
      <main className={styles.page}>
        <p className={styles.muted}>Loading…</p>
      </main>
    );
  }
  if (status !== "ok") {
    return (
      <main className={styles.page}>
        <p className={styles.muted}>
          {status === "notfound"
            ? "There is no enrollment at this address."
            : "The course could not be loaded."}{" "}
          <Link to="/my/courses">Back to my courses.</Link>
        </p>
      </main>
    );
  }

  const completion = enrollment.completion;

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link> / {enrollment.course_code}
      </p>
      <h1 className={styles.title}>{enrollment.title}</h1>
      {enrollment.description && (
        <p className={styles.description}>{enrollment.description}</p>
      )}

      {completion ? (
        <div className={styles.completedPanel}>
          Completed {formatDate(completion.completed_at)} —{" "}
          {completion.credit_awarded} CPE credit in {completion.field_of_study}
          . Certificate {completion.certificate_number}.{" "}
          {completion.certificate_ready ? (
            <a
              href={myCertificateUrl(completion.completion_id)}
              target="_blank"
              rel="noreferrer"
            >
              Download certificate (PDF)
            </a>
          ) : (
            "Your certificate will be issued shortly."
          )}
        </div>
      ) : (
        <p className={styles.deadline}>
          {enrollment.status === "expired"
            ? `This enrollment expired on ${formatDate(enrollment.expires_at)}.`
            : `Complete the qualified assessment by ${formatDate(
                enrollment.expires_at
              )}.`}
        </p>
      )}

      <dl className={styles.facts}>
        {enrollment.credit && (
          <>
            <dt>Recommended CPE credit</dt>
            <dd>{enrollment.credit}</dd>
          </>
        )}
        <dt>Field of study</dt>
        <dd>{enrollment.field_of_study}</dd>
        <dt>Program knowledge level</dt>
        <dd>{enrollment.knowledge_level}</dd>
        <dt>Prerequisites</dt>
        <dd>{enrollment.prerequisites}</dd>
        <dt>Advance preparation</dt>
        <dd>{enrollment.advance_preparation}</dd>
      </dl>

      <h2 className={styles.sectionTitle}>Lessons</h2>
      <ol className={styles.lessonList}>
        {enrollment.lessons.map((lesson) => (
          <li key={lesson.package_id} className={styles.lessonRow}>
            <Link
              className={styles.lessonLink}
              to={`/my/courses/${enrollment.enrollment_id}/lessons/${lesson.package_id}`}
            >
              <span className={styles.lessonPosition}>{lesson.position}.</span>
              <span className={styles.lessonTitle}>{lesson.title}</span>
              <span className={styles.lessonMeta}>
                {formatDuration(lesson.furthest_seconds)} /{" "}
                {formatDuration(lesson.duration_seconds)} ·{" "}
                {lesson.review_answered}/{lesson.review_total} answered
              </span>
            </Link>
          </li>
        ))}
      </ol>

      <h2 className={styles.sectionTitle}>Qualified assessment</h2>
      {enrollment.assessment_available ? (
        <Link
          className={styles.action}
          to={`/my/courses/${enrollment.enrollment_id}/assessment`}
        >
          {enrollment.open_attempt_id
            ? "Resume the assessment"
            : enrollment.failed_attempts > 0
              ? `Retake the assessment (${enrollment.retakes_remaining} left)`
              : "Take the assessment"}
        </Link>
      ) : completion ? null : (
        <div className={styles.reasonPanel}>
          <p className={styles.muted}>The assessment is not available yet:</p>
          <ul className={styles.reasonList}>
            {enrollment.assessment_unavailable_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}

export default MyCourse;
