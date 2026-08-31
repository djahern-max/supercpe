import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPolicies } from "../../api/policies";
import SimpleMarkdown from "../../components/SimpleMarkdown/SimpleMarkdown.jsx";
import styles from "./Policies.module.css";

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * The published 8.01 policies (items 8-10), the re-take policy derived
 * from the constants, and — only when the sponsor may claim it — the
 * item 11 sponsor statement. The payload simply lacks the statement
 * otherwise; this page never decides.
 */
function Policies() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPolicies()
      .then((data) => {
        if (!cancelled) setPayload(data);
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
      <h1 className={styles.title}>Policies</h1>
      {error && (
        <p className={styles.muted}>The policies could not be loaded.</p>
      )}
      {!error && payload === null && <p className={styles.muted}>Loading…</p>}

      {payload !== null &&
        payload.policies.map((policy) => (
          // The id anchors the 016 course-page links (/policies#refund).
          <section key={policy.kind} id={policy.kind} className={styles.policy}>
            <h2 className={styles.policyTitle}>{policy.label}</h2>
            <p className={styles.effective}>
              Effective {formatDate(policy.effective_at)}
            </p>
            <SimpleMarkdown markdown={policy.body} />
          </section>
        ))}

      {payload !== null && (
        <section className={styles.policy}>
          <h2 className={styles.policyTitle}>Assessment and re-takes</h2>
          <p className={styles.body}>{payload.retake_policy}</p>
        </section>
      )}

      {payload !== null && payload.sponsor_statement && (
        <section className={styles.policy}>
          <p className={styles.statement}>{payload.sponsor_statement}</p>
        </section>
      )}
    </main>
  );
}

export default Policies;
