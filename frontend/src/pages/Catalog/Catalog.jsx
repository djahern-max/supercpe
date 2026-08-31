import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPublicCourses } from "../../api/courses";
import styles from "./Catalog.module.css";

function formatTotal(totalSeconds) {
  const minutes = Math.round(totalSeconds / 60);
  return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}

function Catalog() {
  const [courses, setCourses] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listPublicCourses()
      .then((data) => {
        if (!cancelled) setCourses(data);
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
      <h1 className={styles.heading}>Courses</h1>
      {error && <p className={styles.muted}>The catalog could not be loaded.</p>}
      {!error && courses === null && <p className={styles.muted}>Loading…</p>}
      {courses !== null && courses.length === 0 && (
        <p className={styles.muted}>There are no published courses yet.</p>
      )}
      {courses !== null &&
        courses.map((course) => (
          <article key={course.course_code} className={styles.entry}>
            <h2 className={styles.entryTitle}>
              <Link to={`/courses/${course.course_code}`}>{course.title}</Link>
            </h2>
            <p className={styles.entryMeta}>
              {course.field_of_study}
              {course.recommended_credit !== null &&
                ` · ${course.recommended_credit} CPE credit${
                  course.recommended_credit === "1.0" ? "" : "s"
                }`}{" "}
              · {course.knowledge_level} · {course.lesson_count}{" "}
              {course.lesson_count === 1 ? "lesson" : "lessons"} ·{" "}
              {formatTotal(course.total_duration_seconds)} of video
            </p>
            {course.description && (
              <p className={styles.entryDescription}>{course.description}</p>
            )}
          </article>
        ))}
    </main>
  );
}

export default Catalog;
