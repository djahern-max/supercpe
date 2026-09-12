import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyState, setMyState } from "../../api/auth";
import { ApiError } from "../../api/client";
import { getMySubscription, openSubscriptionPortal } from "../../api/subscribe";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import { US_JURISDICTIONS } from "../../constants/jurisdictions";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./Account.module.css";

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * 029: the Subscription section — what Stripe last reported, in words:
 * current / renews on / cancels on / past due (update your card) / lapsed /
 * none, the credit consumed, and Manage subscription, which opens the
 * Stripe Customer Portal (cancellation, card update, invoice history live
 * there; superCPE builds none of them).
 */
function SubscriptionSection() {
  const [subscription, setSubscription] = useState(null);
  const [status, setStatus] = useState("loading");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMySubscription()
      .then((data) => {
        if (cancelled) return;
        setSubscription(data);
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleManage = async () => {
    setErrors(null);
    setBusy(true);
    try {
      const { url } = await openSubscriptionPortal();
      window.location.assign(url);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The billing portal could not be opened. Try again in a moment."]);
      }
    }
  };

  const ends = subscription?.current_period_end
    ? formatDate(subscription.current_period_end)
    : null;

  return (
    <section className={styles.card}>
      <h2 className={styles.label}>Subscription</h2>
      {status === "loading" && <p className={styles.muted}>Loading…</p>}
      {status === "error" && (
        <p className={styles.muted}>
          Your subscription could not be loaded. Reload to try again.
        </p>
      )}
      {subscription && subscription.state === "none" && (
        <p className={styles.muted}>
          You do not have a subscription.{" "}
          <Link to="/subscribe">Subscribe for unlimited courses.</Link>
        </p>
      )}
      {subscription && subscription.state === "current" && (
        <p>Your subscription is current{ends && ` and renews on ${ends}`}.</p>
      )}
      {subscription && subscription.state === "cancels_at_period_end" && (
        <p>
          Your subscription is current and cancels on {ends}; you keep
          access until then.
        </p>
      )}
      {subscription && subscription.state === "past_due" && (
        <p className={styles.errorList}>
          Your last subscription payment failed. Update your payment method
          to keep your subscription; Stripe will retry the card.
        </p>
      )}
      {subscription && subscription.state === "lapsed" && (
        <p className={styles.muted}>
          Your subscription has ended{ends && ` (it ran to ${ends})`}. Your
          courses and certificates are kept.{" "}
          <Link to="/subscribe">Subscribe again</Link> to resume.
        </p>
      )}
      {subscription && subscription.credit_applied_cents > 0 && (
        <p className={styles.muted}>
          {formatUsd(subscription.credit_applied_cents)} of prior course
          purchases was credited against your first payment.
        </p>
      )}
      {subscription?.manageable && (
        <button
          className={styles.manageButton}
          type="button"
          disabled={busy}
          onClick={handleManage}
        >
          {busy
            ? "Opening…"
            : subscription.state === "past_due"
              ? "Update payment method"
              : "Manage subscription"}
        </button>
      )}
      {errors && (
        <ul className={styles.errorList}>
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * 020: the participant's account page — their state of licensure, which
 * the course pages' "For your board" hint keys on (their claim about
 * themselves, changeable and clearable at will), and 029's subscription.
 */
function Account() {
  usePageTitle("Account");
  const { account } = useSession();
  const [state, setState] = useState(null);
  const [status, setStatus] = useState("loading");
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMyState()
      .then((data) => {
        if (cancelled) return;
        setState(data.state ?? "");
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = async (event) => {
    const next = event.target.value;
    setState(next);
    setSaved(false);
    setErrors(null);
    try {
      const data = await setMyState(next);
      setState(data.state ?? "");
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The change could not be saved. Try again."]);
      }
    }
  };

  return (
    <main className={styles.page}>
      <p className={styles.breadcrumb}>
        <Link to="/my/courses">My courses</Link>
      </p>
      <h1 className={styles.heading}>Account</h1>
      {account && <p className={styles.muted}>{account.email}</p>}

      <section className={styles.card}>
        <label className={styles.label} htmlFor="account-state">
          State of licensure
        </label>
        {status === "loading" && <p className={styles.muted}>Loading…</p>}
        {status === "error" && (
          <p className={styles.muted}>
            Your state could not be loaded. Reload to try again.
          </p>
        )}
        {status === "ok" && (
          <select
            id="account-state"
            className={styles.select}
            value={state}
            onChange={handleChange}
          >
            <option value="">Not set</option>
            {Object.entries(US_JURISDICTIONS).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        )}
        <p className={styles.muted}>
          Used to show what your board's rules mean for a course's
          recommended credit, when superCPE has verified them. Optional;
          it never appears on a certificate.
        </p>
        {saved && <p className={styles.saved}>Saved.</p>}
        {errors && (
          <ul className={styles.errorList}>
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
      </section>

      <SubscriptionSection />

      <p className={styles.muted}>
        <Link to="/change-password">Change your password</Link>
      </p>
    </main>
  );
}

export default Account;
