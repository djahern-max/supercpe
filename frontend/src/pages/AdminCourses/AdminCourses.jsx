import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import { createCourse, listCourses } from "../../api/admin";
import styles from "./AdminCourses.module.css";

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

function AdminCourses() {
  const navigate = useNavigate();
  // On a 401 the session died server-side; re-checking /me makes
  // RequireRole redirect to /login.
  const { refresh: refreshSession } = useSession();
  const [courses, setCourses] = useState(null);
  const [listError, setListError] = useState(null);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [createErrors, setCreateErrors] = useState(null);

  const refresh = useCallback(() => {
    listCourses()
      .then((data) => {
        setCourses(data);
        setListError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setListError("Could not load courses. Is the backend running?");
      });
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = async (event) => {
    event.preventDefault();
    setCreating(true);
    setCreateErrors(null);
    try {
      const course = await createCourse({
        course_code: code.trim(),
        title: title.trim(),
      });
      navigate(`/admin/courses/${course.course_code}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setCreateErrors(err.data.errors);
      } else if (err instanceof ApiError && err.status === 401) {
        refreshSession();
      } else {
        setCreateErrors(["Could not create the course. Try again."]);
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Courses</h1>

      <form className={styles.createRow} onSubmit={handleCreate}>
        <input
          className={styles.input}
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Course code (e.g. ASC842-PCX)"
        />
        <input
          className={styles.inputWide}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Title"
        />
        <button
          className={styles.button}
          type="submit"
          disabled={!code.trim() || !title.trim() || creating}
        >
          {creating ? "Creating…" : "Create course"}
        </button>
      </form>
      <ErrorPanel errors={createErrors} />

      {listError && <div className={styles.errorPanel}>{listError}</div>}
      {!listError && courses === null && (
        <p className={styles.muted}>Loading courses…</p>
      )}
      {courses !== null && courses.length === 0 && (
        <p className={styles.muted}>No courses yet. Create one above.</p>
      )}
      {courses !== null && courses.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Title</th>
              <th>Lessons</th>
              <th>Credit</th>
              <th>Status</th>
              <th>Last content change</th>
            </tr>
          </thead>
          <tbody>
            {courses.map((course) => (
              <tr
                key={course.id}
                className={styles.row}
                onClick={() => navigate(`/admin/courses/${course.course_code}`)}
              >
                <td>{course.course_code}</td>
                <td>{course.title}</td>
                <td>{course.lesson_count}</td>
                <td>
                  {course.credit_award ?? "—"}
                  {course.credit_is_stale && (
                    <span className={styles.staleMark}> stale</span>
                  )}
                </td>
                <td>{course.status}</td>
                <td>{new Date(course.content_updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

export default AdminCourses;
