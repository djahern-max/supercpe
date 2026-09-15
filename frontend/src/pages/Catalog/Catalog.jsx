import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPublicCourses } from "../../api/courses";
import { resolveMediaUrl } from "../../api/client";
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

// 035: everything that is not the credit or the price, as one quiet
// line. Five plain facts do not deserve five bordered pills, and a
// missing fact drops out rather than leaving a stray separator.
function metaLine(course) {
  return [
    course.field_of_study,
    course.knowledge_level,
    `${course.lesson_count} ${course.lesson_count === 1 ? "lesson" : "lessons"}`,
    ...formatLength(course),
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * 035: one horizontal card per course — artwork left, text right, the
 * credit figure and the price at the top of the text column. The credit
 * amount is the one fact a licensed CPA scans for, so it is the only
 * thing on the card given any weight.
 *
 * `thumbnail_url` is null for most courses on day one; the card keeps
 * its shape and the text takes the full width. No placeholder graphic:
 * a grey box with an icon is a picture of nothing.
 *
 * `alt=""` is deliberate. The title beside the artwork is the link's
 * accessible name, and describing decoration a second time is noise in
 * a screen reader.
 */
function CourseCard({ course }) {
  const credits =
    course.recommended_credit !== null
      ? `${course.recommended_credit} credit${
          course.recommended_credit === "1.0" ? "" : "s"
        }`
      : null;

  return (
    <li className={styles.card}>
      <Link className={styles.cardLink} to={`/courses/${course.course_code}`}>
        {course.thumbnail_url && (
          <img
            className={styles.artwork}
            src={resolveMediaUrl(course.thumbnail_url)}
            alt=""
            loading="lazy"
            width="240"
            height="135"
          />
        )}
        <div className={styles.body}>
          <div className={styles.head}>
            <h2 className={styles.title}>{course.title}</h2>
            {course.price_cents !== null && (
              <p className={styles.price}>{formatUsd(course.price_cents)}</p>
            )}
          </div>
          {credits && <p className={styles.credits}>{credits}</p>}
          <p className={styles.meta}>{metaLine(course)}</p>
          {course.description && (
            <p className={styles.description}>{course.description}</p>
          )}
        </div>
      </Link>
    </li>
  );
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
        <p className={styles.muted}>No courses are published yet.</p>
      )}
      {courses !== null && courses.length > 0 && (
        <ul className={styles.list}>
          {courses.map((course) => (
            <CourseCard key={course.course_code} course={course} />
          ))}
        </ul>
      )}
    </main>
  );
}

export default Catalog;
