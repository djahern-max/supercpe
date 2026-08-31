import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getCheckoutStatus } from "../../api/checkout";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./PurchaseSuccess.module.css";

const POLL_MS = 2000;
// After this long, be honest that the confirmation is unusually slow.
const SLOW_AFTER_MS = 30000;

// 018: the browser landing here proves nothing — only the webhook
// creates the enrollment — so this page polls the payment's status until
// it does, then links to the course.
function PurchaseSuccess() {
  usePageTitle("Purchase");
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [payment, setPayment] = useState(null);
  const [failed, setFailed] = useState(false);
  const [slow, setSlow] = useState(false);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    if (!sessionId) return undefined;
    let cancelled = false;
    let timer = null;

    const poll = async () => {
      try {
        const data = await getCheckoutStatus(sessionId);
        if (cancelled) return;
        setPayment(data);
        if (data.status === "paid" && data.enrollment_id !== null) return;
      } catch {
        if (cancelled) return;
        setFailed(true);
        return;
      }
      if (Date.now() - startedAt.current > SLOW_AFTER_MS) setSlow(true);
      timer = setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId]);

  if (!sessionId || failed) {
    return (
      <main className={styles.page}>
        <h1 className={styles.heading}>Payment</h1>
        <p className={styles.muted}>
          This payment could not be looked up. If you completed a payment,
          your course is on <Link to="/my/courses">your courses page</Link>{" "}
          once it is confirmed — make sure you are signed in with the
          account that paid.
        </p>
      </main>
    );
  }

  const confirmed = payment?.status === "paid" && payment.enrollment_id !== null;

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>
        {confirmed ? "You're enrolled" : "Confirming your payment"}
      </h1>
      {confirmed ? (
        <>
          <p>
            Your payment for <strong>{payment.course_title}</strong> is
            confirmed and your one-year enrollment has started. Stripe
            emails your receipt.
          </p>
          <Link
            className={styles.startButton}
            to={`/my/courses/${payment.enrollment_id}`}
          >
            Start the course
          </Link>
        </>
      ) : (
        <>
          <p className={styles.spinnerRow}>
            <span className={styles.spinner} aria-hidden="true" />
            Waiting for Stripe to confirm your payment. This usually takes
            a few seconds.
          </p>
          {slow && (
            <p className={styles.muted}>
              The confirmation is taking longer than usual. It is safe to
              leave this page — the course appears on{" "}
              <Link to="/my/courses">your courses page</Link> the moment it
              lands.
              {payment?.support_email &&
                ` If it still has not after a while, write to ${payment.support_email}.`}
            </p>
          )}
        </>
      )}
    </main>
  );
}

export default PurchaseSuccess;
