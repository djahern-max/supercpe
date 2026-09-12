import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getSubscribeStatus } from "../../api/subscribe";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "../PurchaseSuccess/PurchaseSuccess.module.css";

const POLL_MS = 2000;
// After this long, be honest that the confirmation is unusually slow.
const SLOW_AFTER_MS = 30000;

// 029: the browser landing here proves nothing — only the webhook makes
// the subscription current — so this page polls the session's status
// until it does, then links to the catalog (018's pattern).
function SubscribeSuccess() {
  usePageTitle("Subscription");
  const { refresh } = useSession();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [state, setState] = useState(null);
  const [failed, setFailed] = useState(false);
  const [slow, setSlow] = useState(false);
  const startedAt = useRef(null);

  useEffect(() => {
    if (!sessionId) return undefined;
    startedAt.current = Date.now();
    let cancelled = false;
    let timer = null;

    const poll = async () => {
      try {
        const data = await getSubscribeStatus(sessionId);
        if (cancelled) return;
        setState(data);
        if (data.current) {
          // The header's Subscribe link keys on the session's own view.
          refresh();
          return;
        }
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
  }, [sessionId, refresh]);

  if (!sessionId || failed) {
    return (
      <main className={styles.page}>
        <h1 className={styles.heading}>Subscription</h1>
        <p className={styles.muted}>
          This subscription could not be looked up. If you completed a
          payment, your subscription shows on{" "}
          <Link to="/account">your account page</Link> once it is confirmed
          — make sure you are signed in with the account that paid.
        </p>
      </main>
    );
  }

  const confirmed = state?.current === true;

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>
        {confirmed ? "You're subscribed" : "Confirming your subscription"}
      </h1>
      {confirmed ? (
        <>
          <p>
            Your subscription is active
            {state.current_period_end &&
              ` until ${new Date(state.current_period_end).toLocaleDateString(
                undefined,
                { day: "numeric", month: "short", year: "numeric" }
              )}`}
            . Stripe emails your receipt.
            {state.credit_applied_cents > 0 &&
              ` ${formatUsd(state.credit_applied_cents)} of prior course purchases was credited.`}
          </p>
          <Link className={styles.startButton} to="/courses">
            Choose a course
          </Link>
        </>
      ) : (
        <>
          <p className={styles.spinnerRow}>
            <span className={styles.spinner} aria-hidden="true" />
            Waiting for Stripe to confirm your subscription. This usually
            takes a few seconds.
          </p>
          {slow && (
            <p className={styles.muted}>
              The confirmation is taking longer than usual. It is safe to
              leave this page — your subscription appears on{" "}
              <Link to="/account">your account page</Link> the moment it
              lands.
              {state?.support_email &&
                ` If it still has not after a while, write to ${state.support_email}.`}
            </p>
          )}
        </>
      )}
    </main>
  );
}

export default SubscribeSuccess;
