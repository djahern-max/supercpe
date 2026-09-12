import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listMyCourses, myCertificateUrl } from "../../api/my";
import EvaluationForm from "../../components/EvaluationForm/EvaluationForm.jsx";
import RenewEnrollment from "../../components/RenewEnrollment/RenewEnrollment.jsx";
import usePageTitle from "../../hooks/usePageTitle";
import { retakeLabel } from "../MyLesson/nextStep.js";
import styles from "./MyCourses.module.css";
import { lessonsProgressLabel } from "./progressLabel.js";

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * The participant home: each enrollment as a card with one primary action —
 * Continue reading / Take the qualified assessment / Re-take (N left) /
 * View certificate / Expired. 027: the same next action the course page
 * shows, in the same words; an enrollment with no sittings left points
 * at the course page, where the exhausted notice says what that means.
 */
function PrimaryAction({ enrollment }) {
  const to = `/my/courses/${enrollment.enrollment_id}`;
  const navigate = useNavigate();
  if (enrollment.status === "completed") {
    if (enrollment.completion?.certificate_ready) {
      return (
        <a
          className={styles.action}
          href={myCertificateUrl(enrollment.completion.completion_id)}
          target="_blank"
          rel="noreferrer"
        >
          View certificate
        </a>
      );
    }
    return (
      <span className={styles.mutedAction}>
        Certificate will be issued shortly
      </span>
    );
  }
  if (enrollment.status === "expired") {
    // 028: paid and not completed — a new enrollment at no charge, then
    // straight to its course page.
    return enrollment.renewable ? (
      <RenewEnrollment
        courseCode={enrollment.course_code}
        className={styles.actionButton}
        onRenewed={(renewed) =>
          navigate(`/my/courses/${renewed.enrollment_id}`)
        }
      />
    ) : (
      <span className={styles.mutedAction}>Expired</span>
    );
  }
  if (enrollment.open_attempt_id) {
    return (
      <Link className={styles.action} to={`${to}/assessment`}>
        Resume the assessment
      </Link>
    );
  }
  if (enrollment.assessment_available) {
    return (
      <Link className={styles.action} to={`${to}/assessment`}>
        {retakeLabel(enrollment)}
      </Link>
    );
  }
  if (enrollment.retakes_remaining === 0) {
    return (
      <Link className={styles.action} to={to}>
        No re-takes left — see your options
      </Link>
    );
  }
  const verb =
    enrollment.lessons_kind === "text"
      ? "Continue reading"
      : enrollment.lessons_kind === "video"
        ? "Continue watching"
        : "Continue";
  return (
    <Link className={styles.action} to={to}>
      {verb}
    </Link>
  );
}

function MyCourses() {
  usePageTitle("My courses");
  const [enrollments, setEnrollments] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listMyCourses()
      .then((data) => {
        if (!cancelled) setEnrollments(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className={styles.page}>
      {/* 027: the email, Account link, and Sign out that sat here are in
          the 025 site header; the page keeps only its heading. */}
      <h1 className={styles.heading}>My courses</h1>

      {error && (
        <p className={styles.muted}>Your courses could not be loaded.</p>
      )}
      {!error && enrollments === null && (
        <p className={styles.muted}>Loading…</p>
      )}
      {enrollments !== null && enrollments.length === 0 && (
        <p className={styles.muted}>
          You are not enrolled in any course yet.{" "}
          <Link to="/courses">See the courses.</Link>
        </p>
      )}

      {(enrollments ?? []).map((enrollment) => (
        <article key={enrollment.enrollment_id} className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>
              <Link to={`/my/courses/${enrollment.enrollment_id}`}>
                {enrollment.title}
              </Link>
            </h2>
            <span className={styles[`status_${enrollment.status}`]}>
              {enrollment.status}
            </span>
          </div>
          <p className={styles.cardMeta}>
            {enrollment.credit && `${enrollment.credit} CPE credit · `}
            {enrollment.status === "completed" && enrollment.completion
              ? `Completed ${formatDate(enrollment.completion.completed_at)}`
              : `Complete by ${formatDate(enrollment.expires_at)}`}
          </p>
          <p className={styles.cardProgress}>
            {lessonsProgressLabel(enrollment)} · {enrollment.review_answered}{" "}
            of {enrollment.review_total} review questions answered
          </p>
          <PrimaryAction enrollment={enrollment} />
          {enrollment.completion?.evaluation_requested && (
            <EvaluationForm
              completionId={enrollment.completion.completion_id}
            />
          )}
        </article>
      ))}

      <p className={styles.footerLink}>
        <Link to="/how-it-works">How a course works</Link>
      </p>
    </main>
  );
}

export default MyCourses;
