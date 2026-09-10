import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPublicCourses } from "../../api/courses";
import { formatUsd } from "../../constants/money";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./Catalog.module.css";

// 023b: how long the course is, in the medium it is in. A text course
// is "study guide · N sections"; a video course is its minutes. The
// seconds on a text course are its supplemental clips (7.02.7), so the
// video part shows only when it rounds to a minute or more — never
// "0 minutes of video" beside a study guide. No reading-time estimate:
// beside the computed credit it would read as a second credit figure.
function formatLength(course) {
  const parts = [];
  if (course.total_section_count > 0) {
    parts.push(
      `study guide · ${course.total_section_count} ${
        course.total_section_count === 1 ? "section" : "sections"
      }`
    );
  }
  const minutes = Math.round(course.total_duration_seconds / 60);
  if (minutes > 0) {
    parts.push(minutes === 1 ? "1 minute of video" : `${minutes} minutes of video`);
  }
  return parts;
}

function Catalog() {
  usePageTitle("Courses");
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
              {course.lesson_count === 1 ? "lesson" : "lessons"}
              {formatLength(course).map((part) => ` · ${part}`)}
              {course.price_cents !== null &&
                ` · ${formatUsd(course.price_cents)}`}
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
