import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../../auth/SessionContext.jsx";
import { listMyCourses, myCertificateUrl } from "../../api/my";
import EvaluationForm from "../../components/EvaluationForm/EvaluationForm.jsx";
import styles from "./MyCourses.module.css";

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * The participant home: each enrollment as a card with one primary action —
 * Continue / Take the assessment / Retake (N left) / View certificate /
 * Expired.
 */
function PrimaryAction({ enrollment }) {
  const to = `/my/courses/${enrollment.enrollment_id}`;
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
    return <span className={styles.mutedAction}>Expired</span>;
  }
  if (enrollment.open_attempt_id) {
    return (
      <Link className={styles.action} to={`${to}/assessment`}>
        Resume the assessment
      </Link>
    );
  }
  if (enrollment.assessment_available) {
    const label =
      enrollment.failed_attempts > 0
        ? `Retake the assessment (${enrollment.retakes_remaining} left)`
        : "Take the assessment";
    return (
      <Link className={styles.action} to={`${to}/assessment`}>
        {label}
      </Link>
    );
  }
  return (
    <Link className={styles.action} to={to}>
      Continue
    </Link>
  );
}

function MyCourses() {
  const navigate = useNavigate();
  const { account, signOut } = useSession();
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

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.heading}>My courses</h1>
        <span className={styles.spacer} />
        {account && <span className={styles.who}>{account.email}</span>}
        <button
          className={styles.signOut}
          type="button"
          onClick={handleSignOut}
        >
          Sign out
        </button>
      </header>

      {error && (
        <p className={styles.muted}>Your courses could not be loaded.</p>
      )}
      {!error && enrollments === null && (
        <p className={styles.muted}>Loading…</p>
      )}
      {enrollments !== null && enrollments.length === 0 && (
        <p className={styles.muted}>
          You are not enrolled in any course yet.
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
            {enrollment.lessons_watched} of {enrollment.lessons_total} lessons
            watched · {enrollment.review_answered} of{" "}
            {enrollment.review_total} review questions answered
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
