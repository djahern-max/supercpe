import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { getHealth } from "./api/health";
import AdminAssessmentPreview from "./pages/AdminAssessmentPreview/AdminAssessmentPreview.jsx";
import AdminCourseAttempts from "./pages/AdminCourseAttempts/AdminCourseAttempts.jsx";
import AdminCourseDetail from "./pages/AdminCourseDetail/AdminCourseDetail.jsx";
import AdminCoursePreview from "./pages/AdminCoursePreview/AdminCoursePreview.jsx";
import AdminCourses from "./pages/AdminCourses/AdminCourses.jsx";
import AdminPackages from "./pages/AdminPackages/AdminPackages.jsx";
import AdminSponsor from "./pages/AdminSponsor/AdminSponsor.jsx";
import Catalog from "./pages/Catalog/Catalog.jsx";
import CoursePage from "./pages/CoursePage/CoursePage.jsx";
import styles from "./App.module.css";

function Home() {
  const [connected, setConnected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then(() => {
        if (!cancelled) setConnected(true);
      })
      .catch(() => {
        if (!cancelled) setConnected(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>
        super<span className={styles.accent}>CPE</span>
      </h1>
      {connected !== null && (
        <span
          className={connected ? styles.pillConnected : styles.pillUnreachable}
        >
          {connected ? "Backend connected" : "Backend unreachable"}
        </span>
      )}
    </main>
  );
}

function NotFound() {
  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>404</h1>
      <p>There is nothing at this address.</p>
    </main>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/courses" element={<Catalog />} />
      <Route path="/courses/:code" element={<CoursePage />} />
      <Route path="/admin/courses" element={<AdminCourses />} />
      <Route path="/admin/courses/:code" element={<AdminCourseDetail />} />
      <Route path="/admin/courses/:code/attempts" element={<AdminCourseAttempts />} />
      <Route path="/admin/courses/:code/preview" element={<AdminCoursePreview />} />
      <Route
        path="/admin/courses/:code/preview/assessment"
        element={<AdminAssessmentPreview />}
      />
      <Route
        path="/admin/courses/:code/preview/:packageId"
        element={<AdminCoursePreview />}
      />
      <Route path="/admin/packages" element={<AdminPackages />} />
      <Route path="/admin/sponsor" element={<AdminSponsor />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default App;
