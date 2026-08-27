import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getPublicCourse } from "../../api/courses";
import styles from "./CoursePage.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

// The 8.01 disclosure page: every fact a potential participant needs to
// assess the course, laid out in reading order. The fields are the page.
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

      <h2 className={styles.sectionTitle}>Who this course is for</h2>
      <dl className={styles.facts}>
        {course.recommended_credit !== null && (
          <>
            <dt>Recommended CPE credit</dt>
            <dd>
              {course.recommended_credit}
              <span className={styles.creditBasis}>{course.credit_basis}</span>
            </dd>
          </>
        )}
        <dt>Program knowledge level</dt>
        <dd>{course.knowledge_level}</dd>
        <dt>Prerequisites</dt>
        <dd>{course.prerequisites}</dd>
        <dt>Advance preparation</dt>
        <dd>{course.advance_preparation}</dd>
        <dt>Field of study</dt>
        <dd>{course.field_of_study}</dd>
      </dl>

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
    </main>
  );
}

export default CoursePage;
