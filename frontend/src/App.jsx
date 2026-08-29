import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { getHealth } from "./api/health";
import RequireRole from "./auth/RequireRole.jsx";
import { SessionProvider } from "./auth/SessionContext.jsx";
import SiteGate from "./components/SiteGate/SiteGate.jsx";
import AdminAccounts from "./pages/AdminAccounts/AdminAccounts.jsx";
import AdminAssessmentPreview from "./pages/AdminAssessmentPreview/AdminAssessmentPreview.jsx";
import AdminCourseAttempts from "./pages/AdminCourseAttempts/AdminCourseAttempts.jsx";
import AdminCourseDetail from "./pages/AdminCourseDetail/AdminCourseDetail.jsx";
import AdminCoursePreview from "./pages/AdminCoursePreview/AdminCoursePreview.jsx";
import AdminCourses from "./pages/AdminCourses/AdminCourses.jsx";
import AdminPackages from "./pages/AdminPackages/AdminPackages.jsx";
import AdminSmes from "./pages/AdminSmes/AdminSmes.jsx";
import AdminSponsor from "./pages/AdminSponsor/AdminSponsor.jsx";
import Catalog from "./pages/Catalog/Catalog.jsx";
import ChangePassword from "./pages/ChangePassword/ChangePassword.jsx";
import CoursePage from "./pages/CoursePage/CoursePage.jsx";
import Login from "./pages/Login/Login.jsx";
import MyAssessment from "./pages/MyAssessment/MyAssessment.jsx";
import MyCourse from "./pages/MyCourse/MyCourse.jsx";
import MyCourses from "./pages/MyCourses/MyCourses.jsx";
import MyLesson from "./pages/MyLesson/MyLesson.jsx";
import ReviewCourse from "./pages/ReviewCourse/ReviewCourse.jsx";
import ReviewHome from "./pages/ReviewHome/ReviewHome.jsx";
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

const admin = (page) => <RequireRole roles={["admin"]}>{page}</RequireRole>;
const preview = (page) => (
  <RequireRole roles={["admin", "reviewer"]}>{page}</RequireRole>
);
const participant = (page) => (
  <RequireRole roles={["participant"]}>{page}</RequireRole>
);

function App() {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/" element={<SiteGate><Home /></SiteGate>} />
        <Route path="/courses" element={<SiteGate><Catalog /></SiteGate>} />
        <Route
          path="/courses/:code"
          element={<SiteGate><CoursePage /></SiteGate>}
        />
        {/* Reachable but unlinked; staff and testers know the address. */}
        <Route path="/login" element={<Login />} />
        <Route path="/change-password" element={<ChangePassword />} />
        <Route path="/my/courses" element={participant(<MyCourses />)} />
        <Route
          path="/my/courses/:enrollmentId"
          element={participant(<MyCourse />)}
        />
        <Route
          path="/my/courses/:enrollmentId/lessons/:packageId"
          element={participant(<MyLesson />)}
        />
        <Route
          path="/my/courses/:enrollmentId/assessment"
          element={participant(<MyAssessment />)}
        />
        <Route path="/review" element={preview(<ReviewHome />)} />
        <Route path="/review/courses/:code" element={preview(<ReviewCourse />)} />
        <Route path="/admin/courses" element={admin(<AdminCourses />)} />
        <Route path="/admin/courses/:code" element={admin(<AdminCourseDetail />)} />
        <Route
          path="/admin/courses/:code/attempts"
          element={admin(<AdminCourseAttempts />)}
        />
        <Route
          path="/admin/courses/:code/preview"
          element={preview(<AdminCoursePreview />)}
        />
        <Route
          path="/admin/courses/:code/preview/assessment"
          element={preview(<AdminAssessmentPreview />)}
        />
        <Route
          path="/admin/courses/:code/preview/:packageId"
          element={preview(<AdminCoursePreview />)}
        />
        <Route path="/admin/packages" element={admin(<AdminPackages />)} />
        <Route path="/admin/smes" element={admin(<AdminSmes />)} />
        <Route path="/admin/sponsor" element={admin(<AdminSponsor />)} />
        <Route path="/admin/accounts" element={admin(<AdminAccounts />)} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </SessionProvider>
  );
}

export default App;
