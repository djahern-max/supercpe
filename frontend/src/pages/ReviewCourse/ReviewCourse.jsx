import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getReviewCourse, recordReview } from "../../api/review";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import { ReviewHeader } from "../ReviewHome/ReviewHome.jsx";
import styles from "./ReviewCourse.module.css";

const EMPTY_FORM = {
  reviewer_id: "",
  reviewed_at: new Date().toISOString().slice(0, 10),
  decision: "approved",
  notes: "",
  impractical_basis: "",
};

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * One course as the reviewer sees it: read-only facts, a preview link into
 * the player and assessment, the review history, and the record-review
 * form — the 008 form, now entered in the first person. The named reviewer
 * (an SME record) is the 4.02.1 qualification; the login only records who
 * typed it in.
 */
function ReviewCourse() {
  const { code } = useParams();
  const { refresh: refreshSession } = useSession();
  const [course, setCourse] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showImpractical, setShowImpractical] = useState(false);
  const [formErrors, setFormErrors] = useState(null);
  const [recording, setRecording] = useState(false);

  const refresh = useCallback(() => {
    getReviewCourse(code)
      .then(setCourse)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else if (err instanceof ApiError && err.status === 404)
          setError("There is no course with this code.");
        else setError("Could not load the course. Is the backend running?");
      });
  }, [code, refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleRecord = async () => {
    setRecording(true);
    setFormErrors(null);
    try {
      await recordReview(code, {
        reviewer_id: Number(form.reviewer_id),
        reviewed_at: form.reviewed_at,
        decision: form.decision,
        notes: form.notes,
        impractical_basis: form.impractical_basis.trim() || null,
      });
      setForm(EMPTY_FORM);
      setShowImpractical(false);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setFormErrors(err.data.errors);
      } else if (err instanceof ApiError && err.status === 401) {
        refreshSession();
      } else {
        setFormErrors(["The request failed. Try again."]);
      }
    } finally {
      setRecording(false);
    }
  };

  return (
    <main className={styles.page}>
      <ReviewHeader />
      <p className={styles.breadcrumb}>
        <Link to="/review">Courses</Link> / {code}
      </p>

      {error && <div className={styles.errorPanel}>{error}</div>}
      {!error && course === null && (
        <p className={styles.muted}>Loading course…</p>
      )}

      {course && (
        <>
          <section className={styles.card}>
            <h1 className={styles.heading}>{course.title}</h1>
            <p className={styles.muted}>{course.description}</p>
            <dl className={styles.facts}>
              <div className={styles.fact}>
                <dt>Field of study</dt>
                <dd>{course.field_of_study ?? "—"}</dd>
              </div>
              <div className={styles.fact}>
                <dt>Knowledge level</dt>
                <dd>{course.knowledge_level ?? "—"}</dd>
              </div>
              <div className={styles.fact}>
                <dt>Status</dt>
                <dd>{course.status}</dd>
              </div>
              <div className={styles.fact}>
                <dt>Content last changed</dt>
                <dd>{new Date(course.content_updated_at).toLocaleString()}</dd>
              </div>
            </dl>
            <Link
              className={styles.previewLink}
              to={`/admin/courses/${code}/preview`}
            >
              Preview the course and assessment
            </Link>
            {course.lessons.length > 0 && (
              <ul className={styles.lessonList}>
                {course.lessons.map((lesson) => (
                  <li key={lesson.package_id}>
                    {lesson.position}. {lesson.title}{" "}
                    <span className={styles.muted}>
                      {formatDuration(lesson.duration_seconds)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={styles.card}>
            <h2 className={styles.sectionTitle}>Review history</h2>
            {course.reviews.length === 0 && (
              <p className={styles.muted}>
                No reviews recorded. 4.02 requires a review by someone other
                than the developer before first publication.
              </p>
            )}
            {course.reviews.length > 0 && (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Reviewer</th>
                    <th>Date</th>
                    <th>Decision</th>
                    <th>Recorded by</th>
                    <th>Standing</th>
                  </tr>
                </thead>
                <tbody>
                  {course.reviews.map((review) => (
                    <tr key={review.id}>
                      <td>
                        {review.reviewer_name}
                        {review.reviewer_credentials
                          ? `, ${review.reviewer_credentials}`
                          : ""}
                      </td>
                      <td>{review.reviewed_at}</td>
                      <td>{review.decision.replace("_", " ")}</td>
                      <td>{review.recorded_by}</td>
                      <td>
                        {review.is_current
                          ? "current"
                          : review.is_superseded
                            ? "superseded by a content change"
                            : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 className={styles.subsectionTitle}>Record a review</h3>
            <p className={styles.muted}>
              Name the subject matter expert who performed the review; that
              record, not this login, is the 4.02.1 qualification. Reviews
              are immutable once recorded; corrections are new reviews.
            </p>
            <div className={styles.reviewForm}>
              <select
                className={styles.input}
                value={form.reviewer_id}
                onChange={(event) =>
                  setForm({ ...form, reviewer_id: event.target.value })
                }
              >
                <option value="">Reviewer…</option>
                {course.smes.map((sme) => (
                  <option key={sme.id} value={String(sme.id)}>
                    {sme.name}
                    {sme.credentials ? `, ${sme.credentials}` : ""}
                  </option>
                ))}
              </select>
              <input
                className={styles.input}
                type="date"
                value={form.reviewed_at}
                onChange={(event) =>
                  setForm({ ...form, reviewed_at: event.target.value })
                }
              />
              <select
                className={styles.input}
                value={form.decision}
                onChange={(event) =>
                  setForm({ ...form, decision: event.target.value })
                }
              >
                <option value="approved">Approved</option>
                <option value="changes_requested">Changes requested</option>
              </select>
              <input
                className={styles.input}
                placeholder="Notes"
                value={form.notes}
                onChange={(event) =>
                  setForm({ ...form, notes: event.target.value })
                }
              />
              {!showImpractical ? (
                <button
                  className={styles.linkButton}
                  type="button"
                  onClick={() => setShowImpractical(true)}
                >
                  Advance review was impractical (4.02.1)…
                </button>
              ) : (
                <textarea
                  className={styles.textarea}
                  rows={2}
                  placeholder="The documented basis for the lack of advance content review (4.02.1)"
                  value={form.impractical_basis}
                  onChange={(event) =>
                    setForm({ ...form, impractical_basis: event.target.value })
                  }
                />
              )}
              <button
                className={styles.button}
                type="button"
                disabled={
                  form.reviewer_id === "" || !form.reviewed_at || recording
                }
                onClick={handleRecord}
              >
                {recording ? "Recording…" : "Record review"}
              </button>
            </div>
            <ErrorList errors={formErrors} />
          </section>
        </>
      )}
    </main>
  );
}

function ErrorList({ errors }) {
  if (!errors || errors.length === 0) return null;
  return (
    <div className={styles.errorPanel}>
      <ul className={styles.errorList}>
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

export default ReviewCourse;
