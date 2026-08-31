import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { verifyEmail } from "../../api/register";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./Verify.module.css";

/**
 * 017: the landing page for the emailed verification link. Posts the
 * token once on mount; expired, used, and unknown tokens all show the
 * server's one failure message.
 */
function Verify() {
  usePageTitle("Verify your email");
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [state, setState] = useState(token ? "pending" : "failed");
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then((response) => {
        setMessage(response.message);
        setState("verified");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.data?.errors) {
          setMessage(err.data.errors.join(" "));
        }
        setState("failed");
      });
  }, [token]);

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>
        super<span className={styles.accent}>CPE</span>
      </h1>
      {state === "pending" && <p className={styles.body}>Verifying…</p>}
      {state === "verified" && (
        <>
          <p className={styles.success}>{message}</p>
          <p className={styles.body}>
            <Link to="/login">Sign in</Link>
          </p>
        </>
      )}
      {state === "failed" && (
        <>
          <p className={styles.error}>
            {message ||
              "This page needs the verification link from your email."}
          </p>
          <p className={styles.body}>
            <Link to="/resend-verification">
              Request a new verification email
            </Link>
          </p>
        </>
      )}
    </main>
  );
}

export default Verify;
