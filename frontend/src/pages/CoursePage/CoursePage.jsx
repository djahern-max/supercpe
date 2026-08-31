import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { startCheckout } from "../../api/checkout";
import { ApiError } from "../../api/client";
import { getPublicCourse } from "../../api/courses";
import { listMyCourses } from "../../api/my";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import styles from "./CoursePage.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatDate(isoDate) {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function personLine(person) {
  return person.credentials
    ? `${person.name}, ${person.credentials}`
    : person.name;
}

// 018: the live Registration section. What it shows follows the session:
// sign-in/register links for visitors, price and an Enroll button for a
// participant, "you're enrolled" with a player link once they are. The
// Enroll button redirects to Stripe's hosted Checkout page — card data
// never transits superCPE.
function Registration({ course }) {
  const { account, loading } = useSession();
  const [enrollment, setEnrollment] = useState(null);
  const [checkingOut, setCheckingOut] = useState(false);
  const [errors, setErrors] = useState(null);

  const isParticipant = account?.role === "participant";

  useEffect(() => {
    if (!isParticipant) return undefined;
    let cancelled = false;
    listMyCourses()
      .then((mine) => {
        if (cancelled) return;
        setEnrollment(
          mine.find(
            (e) =>
              e.course_code === course.course_code &&
              (e.status === "active" || e.status === "completed")
          ) ?? null
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isParticipant, course.course_code]);

  const handleEnroll = async () => {
    setErrors(null);
    setCheckingOut(true);
    try {
      const { checkout_url: checkoutUrl } = await startCheckout(
        course.course_code
      );
      window.location.assign(checkoutUrl);
    } catch (err) {
      setCheckingOut(false);
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors([
          "Checkout could not be started. Nothing was charged; try again in a moment.",
        ]);
      }
    }
  };

  const price =
    course.price_cents !== null ? formatUsd(course.price_cents) : null;

  return (
    <section className={styles.registration}>
      <h2 className={styles.registrationTitle}>Registration</h2>
      {loading ? null : enrollment ? (
        <p>
          You're enrolled in this course.{" "}
          <Link to={`/my/courses/${enrollment.enrollment_id}`}>
            {enrollment.status === "completed"
              ? "See your completion."
              : "Continue the course."}
          </Link>
        </p>
      ) : isParticipant ? (
        <>
          {price && <p className={styles.price}>{price}</p>}
          <button
            className={styles.enrollButton}
            type="button"
            disabled={checkingOut}
            onClick={handleEnroll}
          >
            {checkingOut ? "Opening checkout…" : "Enroll"}
          </button>
          <p className={styles.muted}>
            Payment opens on Stripe's secure checkout page. Your one-year
            enrollment starts when the payment succeeds.
          </p>
          {errors && (
            <ul className={styles.errorList}>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
        </>
      ) : account ? (
        <p className={styles.muted}>
          {price && <strong className={styles.price}>{price}. </strong>}
          Only participant accounts can enroll; you are signed in as{" "}
          {account.role}.
        </p>
      ) : (
        <p className={styles.muted}>
          {price && <strong className={styles.price}>{price}. </strong>}
          <Link to="/register">Create an account</Link> or{" "}
          <Link to="/login">sign in</Link> to enroll in this course.
        </p>
      )}
    </section>
  );
}

// The 8.01 disclosure page: every applicable item made available in
// advance, in the Standard's stable order, rendered from the payload with
// no course fact of the page's own. The fields are the page.
function CoursePage() {
  const { code } = useParams();
  const [course, setCourse] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;
    getPublicCourse(code)
      .then((data) => {
        if (cancelled) return;
        setCourse(data);
        setStatus("ok");
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus(err instanceof ApiError && err.status === 404 ? "notfound" : "error");
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (status === "loading") {
    return (
      <main className={styles.page}>
        <p className={styles.muted}>Loading…</p>
      </main>
    );
  }
  if (status === "notfound") {
    return (
      <main className={styles.page}>
        <h1 className={styles.title}>Course not found</h1>
        <p className={styles.muted}>
          There is no published course at this address.{" "}
          <Link to="/courses">See all courses.</Link>
        </p>
      </main>
    );
  }
  if (status === "error") {
    return (
      <main className={styles.page}>
        <p className={styles.muted}>The course could not be loaded.</p>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/courses">Courses</Link>
      </p>
      <h1 className={styles.title}>{course.title}</h1>
      {course.description && (
        <p className={styles.description}>{course.description}</p>
      )}

      <h2 className={styles.sectionTitle}>What this course covers</h2>
      <ol className={styles.outlineList}>
        {course.outline.map((lesson) => (
          <li key={lesson.lesson_id} className={styles.outlineItem}>
            <span className={styles.outlineTitle}>{lesson.title}</span>
            <ul className={styles.outlineObjectives}>
              {lesson.objectives.map((objective) => (
                <li key={`${lesson.lesson_id}-${objective.id}`}>
                  {objective.text}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>

      <h2 className={styles.sectionTitle}>What you will learn</h2>
      {course.objectives.map((group) => (
        <div key={group.lesson_id}>
          {course.objectives.length > 1 && (
            <p className={styles.lessonLabel}>
              Lesson {group.position}
            </p>
          )}
          <ul className={styles.objectiveList}>
            {group.objectives.map((objective) => (
              <li key={`${group.lesson_id}-${objective.id}`}>{objective.text}</li>
            ))}
          </ul>
        </div>
      ))}

      {/* 8.01 items 2-6 in the Standard's order (item 3 is credit and
          field of study together). */}
      <h2 className={styles.sectionTitle}>Program details</h2>
      <dl className={styles.facts}>
        <dt>Type of formal learning program</dt>
        <dd>{course.program_type}</dd>
        {course.recommended_credit !== null && (
          <>
            <dt>Recommended CPE credit</dt>
            <dd>
              {course.recommended_credit}
              <span className={styles.creditBasis}>{course.credit_basis}</span>
            </dd>
          </>
        )}
        <dt>Recommended field of study</dt>
        <dd>{course.field_of_study}</dd>
        <dt>Prerequisites</dt>
        <dd>{course.prerequisites}</dd>
        <dt>Program knowledge level</dt>
        <dd>{course.knowledge_level}</dd>
        <dt>Advance preparation</dt>
        <dd>{course.advance_preparation}</dd>
      </dl>

      {/* 8.01 items 8-10: links to the published policies with the
          current version's effective date, never inlined text. */}
      <h2 className={styles.sectionTitle}>Policies</h2>
      <ul className={styles.policyList}>
        {[
          course.registration_policy,
          course.refund_policy,
          course.complaint_policy,
        ]
          .filter(Boolean)
          .map((policy) => (
            <li key={policy.kind}>
              <Link to={policy.url}>{policy.label} policy</Link>
              <span className={styles.policyEffective}>
                {" "}
                — effective{" "}
                {new Date(policy.effective_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
            </li>
          ))}
        <li>
          <Link to="/how-it-works">How this course works</Link>
        </li>
      </ul>

      <h2 className={styles.sectionTitle}>Lessons</h2>
      <ol className={styles.lessonList}>
        {course.lessons.map((lesson) => (
          <li key={lesson.lesson_id} className={styles.lessonRow}>
            <span>{lesson.title}</span>
            <span className={styles.lessonDuration}>
              {formatDuration(lesson.duration_seconds)}
            </span>
          </li>
        ))}
      </ol>

      {/* 018: the reserved section goes live — price, Enroll, or the
          enrolled state, by session. */}
      <Registration course={course} />

      {/* 8.01 item 11, present in the payload only when the sponsor may
          claim it — this page never decides. */}
      {course.sponsor_statement && (
        <p className={styles.statement}>{course.sponsor_statement}</p>
      )}

      {(course.developed_by || course.reviewed_by) && (
        <p className={styles.provenance}>
          {course.developed_by &&
            `Developed by ${personLine(course.developed_by)}. `}
          {course.reviewed_by &&
            `Reviewed by ${personLine(course.reviewed_by)}` +
              (course.last_reviewed
                ? ` on ${formatDate(course.last_reviewed)}.`
                : ".")}
          {course.last_documented_date &&
            ` Last documented ${formatDate(course.last_documented_date)}.`}
        </p>
      )}
    </main>
  );
}

export default CoursePage;
