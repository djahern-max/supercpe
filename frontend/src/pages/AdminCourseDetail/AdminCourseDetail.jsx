import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import {
  adminCertificateUrl,
  attachLesson,
  auditBundleUrl,
  deleteCourse,
  detachLesson,
  enrollParticipant,
  generateAuditBundle,
  getCourse,
  getCourseEvaluations,
  listAttempts,
  listAuditBundles,
  listCompletions,
  listEnrollments,
  listEvaluationReviews,
  listPackages,
  listSmes,
  moveLesson,
  publishCourse,
  recomputeCredit,
  recordCourseReview,
  recordEvaluationReview,
  renderCertificate,
  setCourseDeveloper,
  setCoursePrice,
  setCourseReviewCycle,
  unpublishCourse,
  updateCourse,
  updateLessonVersion,
} from "../../api/admin";
import {
  centsToDollarsText,
  dollarsToCents,
  formatUsd,
} from "../../constants/money";
import styles from "./AdminCourseDetail.module.css";

const DERIVED_FIELDS = [
  { name: "field_of_study", label: "Field of study" },
  { name: "knowledge_level", label: "Knowledge level" },
  { name: "prerequisites", label: "Prerequisites" },
  { name: "advance_preparation", label: "Advance preparation" },
];

// 4.01.1, quoted beside the technology checkbox.
const TECHNOLOGY_SENTENCE =
  "If technology is used in the development of the program, the content " +
  "developer is responsible for reviewing the content for accuracy (4.01.1).";

const EMPTY_REVIEW_FORM = {
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

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

// Column labels for the four rated 4.04.1 elements; the full prompts are
// in the summary payload.
const EVALUATION_ELEMENTS = [
  { key: "objectives_met", label: "Objectives" },
  { key: "prerequisites_appropriate", label: "Prerequisites" },
  { key: "materials_relevant", label: "Materials" },
  { key: "time_appropriate", label: "Time" },
];

function ErrorPanel({ errors }) {
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

function AdminCourseDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { refresh: refreshSession } = useSession();
  const [course, setCourse] = useState(null);
  const [packages, setPackages] = useState(null);
  const [attempts, setAttempts] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [editErrors, setEditErrors] = useState(null);
  const [priceText, setPriceText] = useState("");
  const [priceErrors, setPriceErrors] = useState(null);
  const [lessonErrors, setLessonErrors] = useState(null);
  const [attachErrors, setAttachErrors] = useState(null);
  const [creditErrors, setCreditErrors] = useState(null);
  const [showCalculation, setShowCalculation] = useState(false);
  const [smes, setSmes] = useState(null);
  const [developerSmeId, setDeveloperSmeId] = useState("");
  const [usedTechnology, setUsedTechnology] = useState(true);
  const [developerErrors, setDeveloperErrors] = useState(null);
  const [reviewForm, setReviewForm] = useState(EMPTY_REVIEW_FORM);
  const [showImpractical, setShowImpractical] = useState(false);
  const [reviewErrors, setReviewErrors] = useState(null);
  const [publishErrors, setPublishErrors] = useState(null);
  const [enrollments, setEnrollments] = useState(null);
  const [completions, setCompletions] = useState(null);
  const [enrollEmail, setEnrollEmail] = useState("");
  const [enrollErrors, setEnrollErrors] = useState(null);
  const [certificateErrors, setCertificateErrors] = useState(null);
  const [evaluations, setEvaluations] = useState(null);
  const [evaluationReviews, setEvaluationReviews] = useState(null);
  const [evaluationReviewNote, setEvaluationReviewNote] = useState("");
  const [informedDeveloper, setInformedDeveloper] = useState(false);
  const [evaluationErrors, setEvaluationErrors] = useState(null);
  const [auditExports, setAuditExports] = useState(null);
  const [includeVideo, setIncludeVideo] = useState(false);
  const [auditErrors, setAuditErrors] = useState(null);
  const [generatingBundle, setGeneratingBundle] = useState(false);

  const handleAuthFailure = useCallback(() => {
    refreshSession();
  }, [refreshSession]);

  const applyCourse = useCallback((data) => {
    setCourse(data);
    setTitle(data.title);
    setDescription(data.description);
    setPriceText(
      data.price_cents !== null ? centsToDollarsText(data.price_cents) : ""
    );
    setDeveloperSmeId(
      data.development.developer_id !== null
        ? String(data.development.developer_id)
        : ""
    );
    setUsedTechnology(data.development.developer_used_technology);
  }, []);

  const refresh = useCallback(() => {
    getCourse(code)
      .then((data) => {
        applyCourse(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) handleAuthFailure();
        else if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setLoadError("Could not load the course. Is the backend running?");
      });
    listPackages()
      .then(setPackages)
      .catch(() => setPackages([]));
    listAttempts(code)
      .then(setAttempts)
      .catch(() => setAttempts([]));
    listSmes()
      .then(setSmes)
      .catch(() => setSmes([]));
    listEnrollments(code)
      .then(setEnrollments)
      .catch(() => setEnrollments([]));
    listCompletions(code)
      .then(setCompletions)
      .catch(() => setCompletions([]));
    getCourseEvaluations(code)
      .then(setEvaluations)
      .catch(() => setEvaluations(null));
    listEvaluationReviews(code)
      .then(setEvaluationReviews)
      .catch(() => setEvaluationReviews([]));
    listAuditBundles(code)
      .then(setAuditExports)
      .catch(() => setAuditExports([]));
  }, [code, applyCourse, handleAuthFailure]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Wraps a mutation call: applies the returned course, routes 422 errors to
  // the right panel, handles auth failure.
  const mutate = async (call, setErrors) => {
    setErrors(null);
    try {
      const data = await call();
      if (data) applyCourse(data);
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else if (err instanceof ApiError && err.status === 401) {
        handleAuthFailure();
      } else {
        setErrors(["The request failed. Try again."]);
      }
      return false;
    }
  };

  if (notFound) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Course {code}</h1>
        <p className={styles.muted}>
          There is no course with this code. <Link to="/admin/courses">Back to courses.</Link>
        </p>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <div className={styles.errorPanel}>{loadError}</div>
      </main>
    );
  }

  if (!course) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <p className={styles.muted}>Loading course…</p>
      </main>
    );
  }

  const dirty = title !== course.title || description !== course.description;
  const published = course.status === "published";
  const attachedIds = new Set(course.lessons.map((lesson) => lesson.package_id));
  const attachable = (packages ?? []).filter(
    (pkg) => !pkg.attached_to && pkg.course_code === course.course_code
  );
  const development = course.development;
  const blockFindings = course.readiness.filter((f) => f.level === "block");
  // 016: 8.01 items the course cannot currently disclose. These block
  // publish too; on a published course they are the flag that it would
  // no longer pass the gate (nothing auto-unpublishes).
  const disclosureMissing = course.disclosure_missing;
  const blockingCount = blockFindings.length + disclosureMissing.length;
  const developerDirty =
    developerSmeId !==
      (development.developer_id !== null
        ? String(development.developer_id)
        : "") || usedTechnology !== development.developer_used_technology;

  const handleSave = () =>
    mutate(
      () => updateCourse(code, { title: title.trim(), description }),
      setEditErrors
    );

  // 018: price is a business fact, not content — editable while
  // published, and publish refuses without one.
  const handleSavePrice = () => {
    const cents = dollarsToCents(priceText);
    if (cents === null || cents <= 0) {
      setPriceErrors(['Enter a dollar amount above zero, like "49.00".']);
      return;
    }
    return mutate(() => setCoursePrice(code, cents), setPriceErrors);
  };

  const handleSaveDeveloper = () =>
    mutate(
      () =>
        setCourseDeveloper(code, Number(developerSmeId), usedTechnology),
      setDeveloperErrors
    );

  const handleRecordReview = async () => {
    const body = {
      reviewer_id: Number(reviewForm.reviewer_id),
      reviewed_at: reviewForm.reviewed_at,
      decision: reviewForm.decision,
      notes: reviewForm.notes,
      impractical_basis: reviewForm.impractical_basis.trim() || null,
    };
    const ok = await mutate(
      () => recordCourseReview(code, body),
      setReviewErrors
    );
    if (ok) {
      setReviewForm(EMPTY_REVIEW_FORM);
      setShowImpractical(false);
    }
  };

  const handleEnroll = async () => {
    setEnrollErrors(null);
    try {
      await enrollParticipant(code, enrollEmail.trim());
      setEnrollEmail("");
      listEnrollments(code).then(setEnrollments).catch(() => {});
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setEnrollErrors(err.data.errors);
      } else if (err instanceof ApiError && err.status === 401) {
        handleAuthFailure();
      } else {
        setEnrollErrors(["The enrollment failed. Try again."]);
      }
    }
  };

  const handleRenderCertificate = async (completionId) => {
    setCertificateErrors(null);
    try {
      await renderCertificate(completionId);
      listCompletions(code).then(setCompletions).catch(() => {});
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setCertificateErrors(err.data.errors);
      } else {
        setCertificateErrors(["The render failed. Try again."]);
      }
    }
  };

  const handleRecordEvaluationReview = async () => {
    setEvaluationErrors(null);
    try {
      await recordEvaluationReview(
        code,
        evaluationReviewNote.trim(),
        informedDeveloper
      );
      setEvaluationReviewNote("");
      setInformedDeveloper(false);
      listEvaluationReviews(code).then(setEvaluationReviews).catch(() => {});
      // The readiness panel may carry evaluation_review_due; refresh it.
      getCourse(code).then(applyCourse).catch(() => {});
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) handleAuthFailure();
      else setEvaluationErrors(["Recording the review failed. Try again."]);
    }
  };

  const handleGenerateBundle = async () => {
    setAuditErrors(null);
    setGeneratingBundle(true);
    try {
      await generateAuditBundle(code, includeVideo);
      listAuditBundles(code).then(setAuditExports).catch(() => {});
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) handleAuthFailure();
      else setAuditErrors(["Generating the bundle failed. Try again."]);
    } finally {
      setGeneratingBundle(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete course ${course.course_code}? Its lessons are detached, not deleted.`)) {
      return;
    }
    const ok = await mutate(async () => {
      await deleteCourse(code);
      return null;
    }, setEditErrors);
    if (ok) navigate("/admin/courses");
  };

  return (
    <main className={styles.page}>
      <AdminNav />
      <p className={styles.breadcrumb}>
        <Link to="/admin/courses">Courses</Link> / {course.course_code}
        <span className={styles.status}>{course.status}</span>
        <Link
          className={styles.previewLink}
          to={`/admin/courses/${code}/preview`}
        >
          Preview
        </Link>
      </p>

      <section className={styles.card}>
        {published && (
          <p className={styles.immutableNote}>
            This course is published and its content is immutable. Unpublish it
            to edit, then record a new review before republishing (4.02).
          </p>
        )}
        <label className={styles.label} htmlFor="course-title">
          Title
        </label>
        <input
          id="course-title"
          className={styles.input}
          value={title}
          disabled={published}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label className={styles.label} htmlFor="course-description">
          Description (the 8.01.1 course announcement copy; required before
          publish)
        </label>
        <textarea
          id="course-description"
          className={styles.textarea}
          rows={4}
          value={description}
          disabled={published}
          onChange={(event) => setDescription(event.target.value)}
        />
        {dirty && !published && (
          <button className={styles.button} type="button" onClick={handleSave}>
            Save
          </button>
        )}
        <ErrorPanel errors={editErrors} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Price</h2>
        <p className={styles.muted}>
          USD. Required before publish (a business rule: a published course
          must be purchasable). Changing it is not retroactive — what each
          participant was charged stays on their payment record.
          {course.price_cents !== null &&
            ` Current price: ${formatUsd(course.price_cents)}.`}
        </p>
        <label className={styles.label} htmlFor="course-price">
          Price in dollars
        </label>
        <input
          id="course-price"
          className={styles.input}
          value={priceText}
          inputMode="decimal"
          placeholder="49.00"
          onChange={(event) => setPriceText(event.target.value)}
        />
        {dollarsToCents(priceText) !== course.price_cents && (
          <button
            className={styles.button}
            type="button"
            onClick={handleSavePrice}
          >
            Save price
          </button>
        )}
        <ErrorPanel errors={priceErrors} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Course facts</h2>
        <p className={styles.muted}>
          These come from the attached lessons and cannot be edited here. Every
          lesson must agree on them.
        </p>
        <dl className={styles.facts}>
          {DERIVED_FIELDS.map((field) => (
            <div key={field.name} className={styles.fact}>
              <dt>{field.label}</dt>
              <dd>{course[field.name] ?? "— no lessons attached —"}</dd>
            </div>
          ))}
          <div className={styles.fact}>
            <dt>Last content change</dt>
            <dd>{new Date(course.content_updated_at).toLocaleString()}</dd>
          </div>
        </dl>
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Credit</h2>
        <ErrorPanel errors={creditErrors} />
        {course.credit.is_stale && (
          <div className={styles.staleLine}>
            <span>Stale: {course.credit.stale_reason}.</span>
            <button
              className={styles.smallButton}
              type="button"
              onClick={() =>
                mutate(() => recomputeCredit(code), setCreditErrors)
              }
            >
              Recompute
            </button>
          </div>
        )}
        {course.credit.award !== null && (
          <>
            <p className={styles.creditAward}>
              {course.credit.award}
              <span className={styles.creditUnit}> CPE credit recommended</span>
            </p>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Term</th>
                  <th>Inputs</th>
                  <th>Minutes</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Words ÷ 180</td>
                  <td>{course.credit.word_count} words</td>
                  <td>{course.credit.word_minutes}</td>
                </tr>
                <tr>
                  <td>A/V minutes</td>
                  <td>{course.credit.av_seconds} s</td>
                  <td>{course.credit.av_minutes}</td>
                </tr>
                <tr>
                  <td>Questions × 1.85</td>
                  <td>{course.credit.question_count} questions</td>
                  <td>{course.credit.question_minutes}</td>
                </tr>
                <tr>
                  <td>Sum</td>
                  <td></td>
                  <td>{course.credit.raw_minutes}</td>
                </tr>
                <tr>
                  <td>÷ 50, raw credit</td>
                  <td></td>
                  <td>{course.credit.raw_credit}</td>
                </tr>
                <tr>
                  <td>Rounded down to one-fifth</td>
                  <td></td>
                  <td>{course.credit.award}</td>
                </tr>
              </tbody>
            </table>
            {course.credit.rows.length > 0 && (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Lesson</th>
                    <th>A/V counted</th>
                    <th>Words counted</th>
                    <th>Review q</th>
                    <th>Assessment q</th>
                  </tr>
                </thead>
                <tbody>
                  {course.credit.rows.map((row) => (
                    <tr key={row.package_id}>
                      <td>{row.position}</td>
                      <td>
                        {row.lesson_id} v{row.version}
                      </td>
                      <td>
                        {row.av_seconds_counted} s
                        {!row.av_is_additional_learning && " (narrates the text)"}
                      </td>
                      <td>{row.words_counted}</td>
                      <td>{row.review_questions}</td>
                      <td>{row.assessment_questions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button
              className={styles.smallButton}
              type="button"
              onClick={() => setShowCalculation((visible) => !visible)}
            >
              {showCalculation ? "Hide calculation" : "Show calculation"}
            </button>
            {showCalculation && (
              <pre className={styles.calculation}>{course.credit.as_text}</pre>
            )}
          </>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Lessons</h2>
        {published && (
          <p className={styles.muted}>
            Lesson controls are disabled while the course is published; its
            content is immutable.
          </p>
        )}
        <ErrorPanel errors={lessonErrors} />
        {course.lessons.length === 0 && (
          <p className={styles.muted}>No lessons attached yet.</p>
        )}
        {course.lessons.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>#</th>
                <th>Lesson</th>
                <th>Version</th>
                <th>Title</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {course.lessons.map((lesson, index) => (
                <tr key={lesson.package_id}>
                  <td>{lesson.position}</td>
                  <td>{lesson.lesson_id}</td>
                  <td>v{lesson.version}</td>
                  <td>{lesson.title}</td>
                  <td>{formatDuration(lesson.duration_seconds)}</td>
                  <td className={styles.actions}>
                    <button
                      className={styles.smallButton}
                      type="button"
                      disabled={published || index === 0}
                      onClick={() =>
                        mutate(
                          () => moveLesson(code, lesson.package_id, "up"),
                          setLessonErrors
                        )
                      }
                    >
                      ↑
                    </button>
                    <button
                      className={styles.smallButton}
                      type="button"
                      disabled={published || index === course.lessons.length - 1}
                      onClick={() =>
                        mutate(
                          () => moveLesson(code, lesson.package_id, "down"),
                          setLessonErrors
                        )
                      }
                    >
                      ↓
                    </button>
                    {lesson.newer_version !== null && (
                      <button
                        className={styles.smallButton}
                        type="button"
                        disabled={published}
                        onClick={() =>
                          mutate(
                            () =>
                              updateLessonVersion(
                                code,
                                lesson.package_id,
                                lesson.newer_package_id
                              ),
                            setLessonErrors
                          )
                        }
                      >
                        Update to v{lesson.newer_version}
                      </button>
                    )}
                    <button
                      className={styles.smallButtonDanger}
                      type="button"
                      disabled={published}
                      onClick={() =>
                        mutate(
                          () => detachLesson(code, lesson.package_id),
                          setLessonErrors
                        )
                      }
                    >
                      Detach
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Development &amp; Review</h2>

        <div className={styles.devRow}>
          <label className={styles.label} htmlFor="course-developer">
            Developer (4.01.1)
          </label>
          <select
            id="course-developer"
            className={styles.input}
            value={developerSmeId}
            onChange={(event) => setDeveloperSmeId(event.target.value)}
          >
            <option value="">— none —</option>
            {(smes ?? []).map((sme) => (
              <option key={sme.id} value={String(sme.id)}>
                {sme.name}
                {sme.credentials ? `, ${sme.credentials}` : ""}
              </option>
            ))}
          </select>
          <label className={styles.checkboxLine}>
            <input
              type="checkbox"
              checked={usedTechnology}
              onChange={(event) => setUsedTechnology(event.target.checked)}
            />
            Technology was used in development
          </label>
          <span className={styles.muted}>{TECHNOLOGY_SENTENCE}</span>
          {developerDirty && developerSmeId !== "" && (
            <button
              className={styles.smallButton}
              type="button"
              onClick={handleSaveDeveloper}
            >
              Save developer
            </button>
          )}
        </div>
        <ErrorPanel errors={developerErrors} />

        <div className={styles.devRow}>
          <label className={styles.label} htmlFor="review-cycle">
            Review cycle (4.01)
          </label>
          <select
            id="review-cycle"
            className={styles.input}
            value={development.review_cycle}
            onChange={(event) =>
              mutate(
                () => setCourseReviewCycle(code, event.target.value),
                setDeveloperErrors
              )
            }
          >
            <option value="annual">Annual — the subject changes frequently</option>
            <option value="biennial">Biennial — at least every two years</option>
          </select>
          {development.review_due_at !== null && (
            <span className={styles.muted}>
              Next review due {development.review_due_at}.
            </span>
          )}
          {development.last_documented_date !== null && (
            <span className={styles.muted}>
              Last documented date (4.01): {development.last_documented_date}.
            </span>
          )}
        </div>

        <h3 className={styles.subsectionTitle}>Review history</h3>
        {development.reviews.length === 0 && (
          <p className={styles.muted}>
            No reviews recorded. 4.02 requires a review by someone other than
            the developer before first publication.
          </p>
        )}
        {development.reviews.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Reviewer</th>
                <th>Date</th>
                <th>Decision</th>
                <th>Notes</th>
                <th>Recorded by</th>
                <th>Standing</th>
              </tr>
            </thead>
            <tbody>
              {development.reviews.map((review) => (
                <tr key={review.id}>
                  <td>
                    {review.reviewer_name}
                    {review.reviewer_credentials
                      ? `, ${review.reviewer_credentials}`
                      : ""}
                  </td>
                  <td>{review.reviewed_at}</td>
                  <td>{review.decision.replace("_", " ")}</td>
                  <td>
                    {review.notes}
                    {review.impractical_basis && (
                      <span className={styles.muted}>
                        {" "}
                        Advance review impractical: {review.impractical_basis}
                      </span>
                    )}
                  </td>
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
        <div className={styles.reviewForm}>
          <select
            className={styles.input}
            value={reviewForm.reviewer_id}
            onChange={(event) =>
              setReviewForm({ ...reviewForm, reviewer_id: event.target.value })
            }
          >
            <option value="">Reviewer…</option>
            {(smes ?? []).map((sme) => (
              <option key={sme.id} value={String(sme.id)}>
                {sme.name}
                {sme.credentials ? `, ${sme.credentials}` : ""}
              </option>
            ))}
          </select>
          <input
            className={styles.input}
            type="date"
            value={reviewForm.reviewed_at}
            onChange={(event) =>
              setReviewForm({ ...reviewForm, reviewed_at: event.target.value })
            }
          />
          <select
            className={styles.input}
            value={reviewForm.decision}
            onChange={(event) =>
              setReviewForm({ ...reviewForm, decision: event.target.value })
            }
          >
            <option value="approved">Approved</option>
            <option value="changes_requested">Changes requested</option>
          </select>
          <input
            className={styles.input}
            placeholder="Notes"
            value={reviewForm.notes}
            onChange={(event) =>
              setReviewForm({ ...reviewForm, notes: event.target.value })
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
              value={reviewForm.impractical_basis}
              onChange={(event) =>
                setReviewForm({
                  ...reviewForm,
                  impractical_basis: event.target.value,
                })
              }
            />
          )}
          <button
            className={styles.button}
            type="button"
            disabled={reviewForm.reviewer_id === "" || !reviewForm.reviewed_at}
            onClick={handleRecordReview}
          >
            Record review
          </button>
          <span className={styles.muted}>
            Reviews are immutable once recorded; corrections are new reviews.
          </span>
        </div>
        <ErrorPanel errors={reviewErrors} />

        <div className={styles.publishRow}>
          {published ? (
            <button
              className={styles.dangerButton}
              type="button"
              onClick={() =>
                mutate(() => unpublishCourse(code), setPublishErrors)
              }
            >
              Unpublish
            </button>
          ) : (
            <button
              className={styles.button}
              type="button"
              onClick={() =>
                mutate(() => publishCourse(code), setPublishErrors)
              }
            >
              Publish
            </button>
          )}
          <span className={styles.muted}>
            {published
              ? `Published ${new Date(development.published_at).toLocaleString()}. Content is immutable while published.`
              : blockingCount === 0
                ? "Readiness is clean; the course can publish."
                : `${blockingCount} blocking finding${blockingCount === 1 ? "" : "s"} below.`}
            {published &&
              course.active_enrollment_count > 0 &&
              ` ${course.active_enrollment_count} participant${
                course.active_enrollment_count === 1 ? " is" : "s are"
              } enrolled on the current versions and will keep them if the course is unpublished.`}
          </span>
        </div>
        {published && disclosureMissing.length > 0 && (
          <p className={styles.findingBlock}>
            This course is published but can no longer disclose every 8.01
            item — it would not pass the publish gate today. Nothing is
            unpublished automatically; the missing items are listed under
            Readiness.
          </p>
        )}
        <ErrorPanel errors={publishErrors} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Readiness</h2>
        <p className={styles.muted}>
          {course.review_counts.counting} counting review question
          {course.review_counts.counting === 1 ? "" : "s"}
          {course.review_counts.required !== null
            ? `; ${course.review_counts.required} required for ${course.credit.award} CPE credit (5.01.2.1)`
            : "; the required count needs a fresh credit measurement"}
          . Two-choice questions do not count.
        </p>
        {course.readiness.length === 0 && disclosureMissing.length === 0 && (
          <p className={styles.muted}>No findings.</p>
        )}
        {course.readiness.map((finding) => (
          <p
            key={finding.code}
            className={
              finding.level === "block"
                ? styles.findingBlock
                : styles.findingWarn
            }
          >
            {finding.level === "block" ? "Blocks publish: " : "Warning: "}
            {finding.message}
          </p>
        ))}
        {disclosureMissing.map((item) => (
          <p key={`disclosure-${item.number}`} className={styles.findingBlock}>
            Blocks publish: 8.01 item {item.number} ({item.name}) cannot be
            disclosed — {item.reason}
          </p>
        ))}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Attempts</h2>
        {attempts === null && <p className={styles.muted}>Loading attempts…</p>}
        {attempts !== null && attempts.length === 0 && (
          <p className={styles.muted}>No assessment attempts yet.</p>
        )}
        {attempts !== null && attempts.length > 0 && (
          <>
            {(() => {
              const graded = attempts.filter((a) => a.submitted_at !== null);
              const passed = graded.filter((a) => a.status === "passed");
              return (
                <p className={styles.muted}>
                  {attempts.length} attempt{attempts.length === 1 ? "" : "s"}
                  {graded.length > 0 &&
                    `; ${Math.round((passed.length / graded.length) * 100)}% of ${graded.length} submitted passed`}
                  . Latest: {new Date(attempts[0].started_at).toLocaleString()}{" "}
                  ({attempts[0].status}).
                </p>
              );
            })()}
            <Link className={styles.previewLink} to={`/admin/courses/${code}/attempts`}>
              View all attempts
            </Link>
          </>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Enrollments</h2>
        <div className={styles.enrollForm}>
          <input
            className={styles.input}
            type="email"
            placeholder="participant@example.com"
            value={enrollEmail}
            onChange={(event) => setEnrollEmail(event.target.value)}
          />
          <button
            className={styles.smallButton}
            type="button"
            disabled={!published || enrollEmail.trim() === ""}
            onClick={handleEnroll}
          >
            Enroll
          </button>
          {!published && (
            <span className={styles.muted}>
              Only published courses can be enrolled in.
            </span>
          )}
        </div>
        <ErrorPanel errors={enrollErrors} />
        {enrollments === null && (
          <p className={styles.muted}>Loading enrollments…</p>
        )}
        {enrollments !== null && enrollments.length === 0 && (
          <p className={styles.muted}>No enrollments yet.</p>
        )}
        {enrollments !== null && enrollments.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Participant</th>
                <th>Status</th>
                <th>Enrolled</th>
                <th>Expires</th>
                <th>Progress</th>
              </tr>
            </thead>
            <tbody>
              {enrollments.map((enrollment) => (
                <tr key={enrollment.id}>
                  <td>{enrollment.email}</td>
                  <td>{enrollment.status}</td>
                  <td>{new Date(enrollment.enrolled_at).toLocaleDateString()}</td>
                  <td>{new Date(enrollment.expires_at).toLocaleDateString()}</td>
                  <td>
                    {enrollment.lessons_watched}/{enrollment.lessons_total}{" "}
                    lessons · {enrollment.review_answered}/
                    {enrollment.review_total} review answers
                    {enrollment.failed_attempts > 0 &&
                      ` · ${enrollment.failed_attempts} failed attempt${enrollment.failed_attempts === 1 ? "" : "s"}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Completions</h2>
        <ErrorPanel errors={certificateErrors} />
        {completions === null && (
          <p className={styles.muted}>Loading completions…</p>
        )}
        {completions !== null && completions.length === 0 && (
          <p className={styles.muted}>No completions yet.</p>
        )}
        {completions !== null && completions.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Participant</th>
                <th>Completed</th>
                <th>Credit</th>
                <th>Certificate</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {completions.map((completion) => (
                <tr key={completion.id}>
                  <td>{completion.email}</td>
                  <td>
                    {new Date(completion.completed_at).toLocaleDateString()}
                    {completion.overdue && (
                      <span className={styles.twoChoiceBadge}>
                        certificate overdue
                      </span>
                    )}
                  </td>
                  <td>
                    {completion.credit_awarded} · {completion.field_of_study}
                  </td>
                  <td>
                    {completion.certificate_number}
                    {completion.certificate_rendered_at === null &&
                      " (not rendered)"}
                  </td>
                  <td className={styles.actions}>
                    {completion.certificate_rendered_at === null && (
                      <button
                        className={styles.smallButton}
                        type="button"
                        onClick={() => handleRenderCertificate(completion.id)}
                      >
                        Render
                      </button>
                    )}
                    {completion.certificate_rendered_at !== null && (
                      <a
                        className={styles.previewLink}
                        href={adminCertificateUrl(completion.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Evaluations</h2>
        <ErrorPanel errors={evaluationErrors} />
        {evaluations === null && (
          <p className={styles.muted}>Loading evaluations…</p>
        )}
        {evaluations !== null && (
          <>
            <p className={styles.muted}>
              {evaluations.summary.n === 0
                ? "No evaluations submitted yet."
                : `${evaluations.summary.n} evaluation(s). ` +
                  EVALUATION_ELEMENTS.map(
                    ({ key, label }) =>
                      `${label}: ${evaluations.summary.elements[key].mean}`
                  ).join(" · ")}
              {" "}Instructor evaluation is not applicable (self study).
            </p>
            {evaluations.developer_name && (
              <p className={styles.muted}>
                4.04.2: inform the developer of record,{" "}
                <strong>{evaluations.developer_name}</strong>, of these
                results (email delivery is a later feature).
              </p>
            )}
            {evaluations.rows.length > 0 && (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Submitted</th>
                    {EVALUATION_ELEMENTS.map(({ key, label }) => (
                      <th key={key}>{label}</th>
                    ))}
                    <th>Comments</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluations.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.submitted_at).toLocaleDateString()}</td>
                      {EVALUATION_ELEMENTS.map(({ key }) => (
                        <td key={key}>{row[key]}</td>
                      ))}
                      <td>{row.comments || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 className={styles.subsectionTitle}>
              Reviews of results (4.04.2)
            </h3>
            {evaluationReviews !== null && evaluationReviews.length > 0 && (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Reviewed</th>
                    <th>By</th>
                    <th>Developer informed</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluationReviews.map((review) => (
                    <tr key={review.id}>
                      <td>
                        {new Date(review.reviewed_at).toLocaleDateString()}
                      </td>
                      <td>{review.reviewed_by_email}</td>
                      <td>{review.informed_developer ? "yes" : "no"}</td>
                      <td>{review.note || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {evaluationReviews !== null && evaluationReviews.length === 0 && (
              <p className={styles.muted}>No review recorded yet.</p>
            )}
            <div className={styles.formRow}>
              <input
                className={styles.input}
                placeholder="Note (optional)"
                value={evaluationReviewNote}
                onChange={(event) =>
                  setEvaluationReviewNote(event.target.value)
                }
              />
              <label className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={informedDeveloper}
                  onChange={(event) =>
                    setInformedDeveloper(event.target.checked)
                  }
                />
                Developer informed
              </label>
              <button
                className={styles.smallButton}
                type="button"
                onClick={handleRecordEvaluationReview}
              >
                Record review of results
              </button>
            </div>
          </>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Audit bundle</h2>
        <p className={styles.muted}>
          The 9.02.2 documentation set for this course as one zip. Every
          generation is kept and logged.
        </p>
        <ErrorPanel errors={auditErrors} />
        <div className={styles.formRow}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={includeVideo}
              onChange={(event) => setIncludeVideo(event.target.checked)}
            />
            Include videos (large — the zip carries every pinned mp4)
          </label>
          <button
            className={styles.smallButton}
            type="button"
            disabled={generatingBundle}
            onClick={handleGenerateBundle}
          >
            {generatingBundle ? "Generating…" : "Generate"}
          </button>
        </div>
        {auditExports !== null && auditExports.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Generated</th>
                <th>By</th>
                <th>Size</th>
                <th>sha256</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {auditExports.map((exportRow) => (
                <tr key={exportRow.id}>
                  <td>{new Date(exportRow.generated_at).toLocaleString()}</td>
                  <td>{exportRow.generated_by_email}</td>
                  <td>{formatBytes(exportRow.size_bytes)}</td>
                  <td>
                    <code title={exportRow.sha256}>
                      {exportRow.sha256.slice(0, 12)}…
                    </code>
                  </td>
                  <td>
                    <a
                      className={styles.previewLink}
                      href={auditBundleUrl(code, exportRow.id)}
                    >
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {auditExports !== null && auditExports.length === 0 && (
          <p className={styles.muted}>No bundle generated yet.</p>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Questions</h2>
        {course.questions.length === 0 && (
          <p className={styles.muted}>No lessons attached yet.</p>
        )}
        {course.questions.map((group) => (
          <div key={group.package_id} className={styles.questionGroup}>
            <h3 className={styles.questionLesson}>
              {group.position}. {group.lesson_id}
            </h3>
            <h4 className={styles.questionKind}>Review</h4>
            {group.review.length === 0 && (
              <p className={styles.muted}>No review questions.</p>
            )}
            {group.review.map((question) => (
              <p key={question.question_key} className={styles.questionLine}>
                <span className={styles.questionMeta}>
                  {question.question_key} · after block {question.after_block}
                </span>
                {question.stem}
                {!question.counts_toward_minimum && (
                  <span className={styles.twoChoiceBadge}>
                    two choices — does not count
                  </span>
                )}
              </p>
            ))}
            <h4 className={styles.questionKind}>Assessment</h4>
            {group.assessment.length === 0 && (
              <p className={styles.muted}>No assessment questions.</p>
            )}
            {group.assessment.map((question) => (
              <p key={question.question_key} className={styles.questionLine}>
                <span className={styles.questionMeta}>
                  {question.question_key}
                </span>
                {question.stem}
              </p>
            ))}
          </div>
        ))}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Attach a lesson</h2>
        <ErrorPanel errors={attachErrors} />
        {packages === null && <p className={styles.muted}>Loading packages…</p>}
        {packages !== null && attachable.length === 0 && (
          <p className={styles.muted}>
            No unattached packages carry course_code {course.course_code}. Ingest
            one on the <Link to="/admin/packages">packages page</Link>.
          </p>
        )}
        {attachable.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Lesson</th>
                <th>Version</th>
                <th>Title</th>
                <th>Level</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {attachable.map((pkg) => (
                <tr key={pkg.id}>
                  <td>{pkg.lesson_id}</td>
                  <td>v{pkg.version}</td>
                  <td>{pkg.title}</td>
                  <td>{pkg.knowledge_level}</td>
                  <td className={styles.actions}>
                    <button
                      className={styles.smallButton}
                      type="button"
                      disabled={published || attachedIds.has(pkg.id)}
                      onClick={async () => {
                        const ok = await mutate(
                          () => attachLesson(code, { package_id: pkg.id }),
                          setAttachErrors
                        );
                        if (ok) refresh();
                      }}
                    >
                      Attach
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.dangerRow}>
        <button className={styles.dangerButton} type="button" onClick={handleDelete}>
          Delete course
        </button>
        <span className={styles.muted}>
          Draft only. Lessons are detached; packages are kept.
        </span>
      </section>
    </main>
  );
}

export default AdminCourseDetail;
