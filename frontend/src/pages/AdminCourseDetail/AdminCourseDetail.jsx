import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import TokenForm from "../../admin/TokenForm.jsx";
import { clearToken, getToken, setToken } from "../../admin/token";
import { ApiError } from "../../api/client";
import {
  attachLesson,
  deleteCourse,
  detachLesson,
  getCourse,
  listAttempts,
  listPackages,
  moveLesson,
  recomputeCredit,
  updateCourse,
  updateLessonVersion,
} from "../../api/admin";
import styles from "./AdminCourseDetail.module.css";

const DERIVED_FIELDS = [
  { name: "field_of_study", label: "Field of study" },
  { name: "knowledge_level", label: "Knowledge level" },
  { name: "prerequisites", label: "Prerequisites" },
  { name: "advance_preparation", label: "Advance preparation" },
];

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

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
  const [token, setTokenState] = useState(getToken());
  const [course, setCourse] = useState(null);
  const [packages, setPackages] = useState(null);
  const [attempts, setAttempts] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [editErrors, setEditErrors] = useState(null);
  const [lessonErrors, setLessonErrors] = useState(null);
  const [attachErrors, setAttachErrors] = useState(null);
  const [creditErrors, setCreditErrors] = useState(null);
  const [showCalculation, setShowCalculation] = useState(false);

  const handleAuthFailure = useCallback(() => {
    clearToken();
    setTokenState(null);
    setCourse(null);
    setPackages(null);
  }, []);

  const applyCourse = useCallback((data) => {
    setCourse(data);
    setTitle(data.title);
    setDescription(data.description);
  }, []);

  const refresh = useCallback(() => {
    if (!token) return;
    getCourse(code, token)
      .then((data) => {
        applyCourse(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) handleAuthFailure();
        else if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setLoadError("Could not load the course. Is the backend running?");
      });
    listPackages(token)
      .then(setPackages)
      .catch(() => setPackages([]));
    listAttempts(code, token)
      .then(setAttempts)
      .catch(() => setAttempts([]));
  }, [token, code, applyCourse, handleAuthFailure]);

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

  if (!token) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Course {code}</h1>
        <TokenForm
          onSubmit={(value) => {
            setToken(value);
            setTokenState(value);
          }}
        />
      </main>
    );
  }

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
  const attachedIds = new Set(course.lessons.map((lesson) => lesson.package_id));
  const attachable = (packages ?? []).filter(
    (pkg) => !pkg.attached_to && pkg.course_code === course.course_code
  );

  const handleSave = () =>
    mutate(
      () => updateCourse(code, { title: title.trim(), description }, token),
      setEditErrors
    );

  const handleDelete = async () => {
    if (!window.confirm(`Delete course ${course.course_code}? Its lessons are detached, not deleted.`)) {
      return;
    }
    const ok = await mutate(async () => {
      await deleteCourse(code, token);
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
        <label className={styles.label} htmlFor="course-title">
          Title
        </label>
        <input
          id="course-title"
          className={styles.input}
          value={title}
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
          onChange={(event) => setDescription(event.target.value)}
        />
        {dirty && (
          <button className={styles.button} type="button" onClick={handleSave}>
            Save
          </button>
        )}
        <ErrorPanel errors={editErrors} />
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
                mutate(() => recomputeCredit(code, token), setCreditErrors)
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
                      disabled={index === 0}
                      onClick={() =>
                        mutate(
                          () => moveLesson(code, lesson.package_id, "up", token),
                          setLessonErrors
                        )
                      }
                    >
                      ↑
                    </button>
                    <button
                      className={styles.smallButton}
                      type="button"
                      disabled={index === course.lessons.length - 1}
                      onClick={() =>
                        mutate(
                          () => moveLesson(code, lesson.package_id, "down", token),
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
                        onClick={() =>
                          mutate(
                            () =>
                              updateLessonVersion(
                                code,
                                lesson.package_id,
                                lesson.newer_package_id,
                                token
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
                      onClick={() =>
                        mutate(
                          () => detachLesson(code, lesson.package_id, token),
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
        <h2 className={styles.sectionTitle}>Readiness</h2>
        <p className={styles.muted}>
          {course.review_counts.counting} counting review question
          {course.review_counts.counting === 1 ? "" : "s"}
          {course.review_counts.required !== null
            ? `; ${course.review_counts.required} required for ${course.credit.award} CPE credit (5.01.2.1)`
            : "; the required count needs a fresh credit measurement"}
          . Two-choice questions do not count.
        </p>
        {course.readiness.length === 0 && (
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
                      disabled={attachedIds.has(pkg.id)}
                      onClick={async () => {
                        const ok = await mutate(
                          () => attachLesson(code, { package_id: pkg.id }, token),
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
