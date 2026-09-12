import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyAssessment, getMyEnrollment, myCertificateUrl } from "../../api/my";
import RetakesExhausted from "../../components/RetakesExhausted/RetakesExhausted.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import { isExhausted } from "./exhausted.js";
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

/** A button that copies `text` and briefly confirms it did. */
function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };
  return (
    <button type="button" className={styles.copyButton} onClick={handleCopy}>
      {copied ? "Copied" : label}
    </button>
  );
}

/**
 * 027: the one next action, as a primary button — never only a status
 * line. Derived from the same fields the reader's completion card reads;
 * the lesson to continue is the first not yet done, in position order.
 */
function NextAction({ enrollment }) {
  const base = `/my/courses/${enrollment.enrollment_id}`;
  const completion = enrollment.completion;
  if (completion) {
    return completion.certificate_ready ? (
      <a
        className={styles.action}
        href={myCertificateUrl(completion.completion_id)}
        target="_blank"
        rel="noreferrer"
      >
        View your certificate
      </a>
    ) : (
      <span className={styles.mutedAction}>
        Your certificate will be issued shortly.
      </span>
    );
  }
  if (enrollment.status === "expired") {
    return (
      <span className={styles.mutedAction}>
        This enrollment expired on {formatDate(enrollment.expires_at)}.
      </span>
    );
  }
  if (enrollment.status === "voided") {
    return (
      <span className={styles.mutedAction}>This enrollment has been voided.</span>
    );
  }
  if (enrollment.open_attempt_id) {
    return (
      <Link className={styles.action} to={`${base}/assessment`}>
        Resume the assessment
      </Link>
    );
  }
  if (enrollment.assessment_available) {
    return (
      <Link className={styles.action} to={`${base}/assessment`}>
        {enrollment.failed_attempts > 0
          ? `Re-take the qualified assessment (${enrollment.retakes_remaining} left)`
          : "Take the qualified assessment"}
      </Link>
    );
  }
  if (isExhausted(enrollment)) return null;
  const remaining = enrollment.lessons
    .filter((l) => !l.done)
    .sort((a, b) => a.position - b.position);
  const next = remaining[0] ?? enrollment.lessons[0];
  if (!next) return null;
  const verb = next.kind === "text" ? "Continue reading" : "Continue watching";
  return (
    <Link className={styles.action} to={`${base}/lessons/${next.package_id}`}>
      {verb} (lesson {next.position} of {enrollment.lessons.length})
    </Link>
  );
}

/**
 * One enrollment: the 004 course facts the participant enrolled on, the
 * lesson list with progress (each mounting the 006 player or the 023
 * reader through the enrollment endpoints), and the assessment link —
 * enabled only when every review question is answered, with the reasons
 * spelled out otherwise.
 *
 * 027: the next action is a primary button under the deadline, and an
 * enrollment with no sittings left shows the shared exhausted notice —
 * once, in place of "not available yet", which is reserved for the case
 * where "yet" is true: unanswered review questions.
 */
function MyCourse() {
  usePageTitle("My course");
  const { enrollmentId } = useParams();
  const [enrollment, setEnrollment] = useState(null);
  const [status, setStatus] = useState("loading");
  // Only read when exhausted: the enrollment detail carries the sittings
  // left, not the sponsor's re-take allowance the notice states.
  const [retakesAllowed, setRetakesAllowed] = useState(null);

  const load = useCallback(() => {
    getMyEnrollment(enrollmentId)
      .then((data) => {
        setEnrollment(data);
        setStatus("ok");
        if (isExhausted(data)) {
          getMyAssessment(enrollmentId)
            .then((info) => setRetakesAllowed(info.retakes_allowed))
            .catch(() => {});
        }
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
  const exhausted = isExhausted(enrollment);
  const lessonsKind = enrollment.lessons.every((l) => l.kind === "text")
    ? "text"
    : enrollment.lessons.every((l) => l.kind !== "text")
      ? "video"
      : "mixed";
  const reasons = enrollment.assessment_unavailable_reasons.filter(
    (reason) => !reason.startsWith("No re-takes left")
  );

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
          {/* 019: the code printed on the certificate and its shareable
              verification link — a board or employer can be handed the
              link instead of the PDF. */}
          <div className={styles.verification}>
            <span className={styles.verificationLabel}>
              Verification code:
            </span>{" "}
            <code className={styles.verificationCode}>
              {completion.verification_code}
            </code>{" "}
            <CopyButton text={completion.verification_code} label="Copy code" />{" "}
            <CopyButton
              text={`${window.location.origin}/certificates/verify/${completion.verification_code}`}
              label="Copy verification link"
            />{" "}
            <Link to={`/certificates/verify/${completion.verification_code}`}>
              Verification page
            </Link>
          </div>
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

      <div className={styles.nextAction}>
        {exhausted ? (
          <RetakesExhausted
            retakesAllowed={retakesAllowed ?? enrollment.failed_attempts - 1}
            lessonsKind={lessonsKind}
          />
        ) : (
          <NextAction enrollment={enrollment} />
        )}
      </div>

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
                {/* A text lesson (023) is read, not watched: reporting a
                    furthest-second against a study guide would say
                    nothing. Its progress is the review questions it has
                    answered, which is also what opens the assessment. */}
                {lesson.kind === "text"
                  ? "Study guide"
                  : `${formatDuration(lesson.furthest_seconds)} / ${formatDuration(
                      lesson.duration_seconds
                    )}`}{" "}
                · {lesson.review_answered}/{lesson.review_total} answered
              </span>
            </Link>
          </li>
        ))}
      </ol>

      {/* The exhausted notice above already says everything about the
          assessment; a second message here would be the two-message
          state the 2026-09-12 walkthrough found. */}
      {!exhausted && (
        <>
          <h2 className={styles.sectionTitle}>Qualified assessment</h2>
          {enrollment.assessment_available ? (
            <Link
              className={styles.action}
              to={`/my/courses/${enrollment.enrollment_id}/assessment`}
            >
              {enrollment.open_attempt_id
                ? "Resume the assessment"
                : enrollment.failed_attempts > 0
                  ? `Re-take the qualified assessment (${enrollment.retakes_remaining} left)`
                  : "Take the qualified assessment"}
            </Link>
          ) : completion ? null : (
            <div className={styles.reasonPanel}>
              <p className={styles.muted}>The assessment is not available yet:</p>
              <ul className={styles.reasonList}>
                {reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </main>
  );
}

export default MyCourse;
