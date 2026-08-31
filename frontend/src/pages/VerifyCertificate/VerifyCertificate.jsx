import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { verifyCertificate } from "../../api/certificates";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./VerifyCertificate.module.css";

/**
 * 019: public certificate verification. `/certificates/verify` is the
 * code-entry box; `/certificates/verify/:code` is the shareable result
 * card. Everything shown comes from the completion-time snapshot the API
 * serves — the page confirms what the certificate says, frozen.
 */
function VerifyCertificate() {
  usePageTitle("Verify a certificate");
  const { code } = useParams();
  const navigate = useNavigate();
  const [input, setInput] = useState(code || "");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState(code ? "loading" : "idle");

  useEffect(() => {
    if (!code) {
      setStatus("idle");
      setResult(null);
      return;
    }
    setStatus("loading");
    verifyCertificate(code)
      .then((data) => {
        setResult(data);
        setStatus("ok");
      })
      .catch((err) => {
        setStatus(
          err instanceof ApiError && err.status === 404 ? "notfound" : "error"
        );
      });
  }, [code]);

  const handleSubmit = (event) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (trimmed) {
      navigate(`/certificates/verify/${encodeURIComponent(trimmed)}`);
    }
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>Verify a certificate</h1>
      <p className={styles.muted}>
        Enter the verification code printed on a certificate of completion.
      </p>
      <form className={styles.form} onSubmit={handleSubmit}>
        <input
          className={styles.input}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Verification code"
          aria-label="Verification code"
        />
        <button className={styles.button} type="submit">
          Verify
        </button>
      </form>

      {status === "loading" && <p className={styles.muted}>Checking…</p>}
      {status === "notfound" && (
        <p className={styles.notFound}>
          No certificate matches that code. Check the code as printed on the
          certificate and try again.
        </p>
      )}
      {status === "error" && (
        <p className={styles.notFound}>
          The certificate could not be checked. Try again.
        </p>
      )}
      {status === "ok" && result && (
        <div className={styles.card}>
          <p className={styles.validBanner}>This certificate is valid.</p>
          <dl className={styles.facts}>
            <dt>Participant</dt>
            <dd>{result.participant_name}</dd>
            <dt>Course</dt>
            <dd>{result.course_title}</dd>
            <dt>CPE credit</dt>
            <dd>
              {result.credit} in {result.field_of_study}
            </dd>
            <dt>Completed</dt>
            <dd>{result.completed_at}</dd>
            <dt>Type of learning program</dt>
            <dd>{result.program_type}</dd>
            <dt>Sponsor</dt>
            <dd>{result.sponsor_name}</dd>
          </dl>
          <p className={styles.muted}>
            These facts were recorded when the credit was earned; later
            changes to the course do not affect them.
          </p>
        </div>
      )}
    </main>
  );
}

export default VerifyCertificate;
