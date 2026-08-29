import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHowItWorks } from "../../api/policies";
import SimpleMarkdown from "../../components/SimpleMarkdown/SimpleMarkdown.jsx";
import styles from "./HowItWorks.module.css";

/**
 * The 4.05.3 item 4 instructions page. The Markdown comes from the
 * backend, where every number is read from the constant that enforces it.
 */
function HowItWorks() {
  const [markdown, setMarkdown] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHowItWorks()
      .then((data) => {
        if (!cancelled) setMarkdown(data.markdown);
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
      <p className={styles.breadcrumb}>
        <Link to="/courses">Courses</Link>
      </p>
      {error && <p className={styles.muted}>The page could not be loaded.</p>}
      {!error && markdown === null && <p className={styles.muted}>Loading…</p>}
      {markdown !== null && <SimpleMarkdown markdown={markdown} />}
    </main>
  );
}

export default HowItWorks;
