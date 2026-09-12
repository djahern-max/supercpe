import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getSubscribeOffer, startSubscribe } from "../../api/subscribe";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import usePageTitle from "../../hooks/usePageTitle";
import styles from "./Subscribe.module.css";

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * 029: the subscription offer — the 8.01 disclosure about the
 * *subscription*: price (the constant, from the payload), term, renewal,
 * cancellation, the viewer's purchase credit when there is one, and
 * links to the registration and refund policies (never restated). No
 * course fact appears here. Signed-out visitors see the page at open
 * with Sign in / Create account in place of the button; the Subscribe
 * button opens Stripe's hosted Checkout — card data never transits
 * superCPE.
 */
function Subscribe() {
  usePageTitle("Subscribe");
  const { account, loading } = useSession();
  const [offer, setOffer] = useState(null);
  const [status, setStatus] = useState("loading");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState(null);

  useEffect(() => {
    if (loading) return undefined;
    let cancelled = false;
    getSubscribeOffer()
      .then((data) => {
        if (cancelled) return;
        setOffer(data);
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [loading, account]);

  const handleSubscribe = async () => {
    setErrors(null);
    setBusy(true);
    try {
      const { checkout_url: checkoutUrl } = await startSubscribe();
      window.location.assign(checkoutUrl);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors([
          "Checkout could not be started. Nothing was charged; try again in a moment.",
        ]);
      }
    }
  };

  const isParticipant = account?.role === "participant";

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>Subscribe</h1>
      {status === "loading" && <p className={styles.muted}>Loading…</p>}
      {status === "error" && (
        <p className={styles.muted}>The offer could not be loaded.</p>
      )}
      {offer && (
        <section className={styles.offer}>
          <p className={styles.price}>
            {formatUsd(offer.price_cents)}
            <span className={styles.per}> per year</span>
          </p>
          <ul className={styles.terms}>
            <li>Unlimited course enrollments for one year.</li>
            <li>Renews automatically at the end of each year.</li>
            <li>Cancel any time; access continues to the end of the period.</li>
            <li>
              Each course you enroll in has its own one-year completion
              window from the day you enroll.
            </li>
          </ul>
          {offer.credit_cents > 0 && (
            <p className={styles.credit}>
              Your {formatUsd(offer.credit_cents)} in course purchases is
              credited: you pay {formatUsd(offer.pay_today_cents)} today.
            </p>
          )}
          {offer.subscribed ? (
            <p className={styles.muted}>
              You already have a current subscription.{" "}
              <Link to="/account">Manage it from your account.</Link>
            </p>
          ) : isParticipant ? (
            <>
              <button
                className={styles.button}
                type="button"
                disabled={busy}
                onClick={handleSubscribe}
              >
                {busy ? "Opening checkout…" : "Subscribe"}
              </button>
              <p className={styles.muted}>
                Payment opens on Stripe's secure checkout page. Your
                subscription starts when the payment succeeds.
              </p>
            </>
          ) : account ? (
            <p className={styles.muted}>
              Only participant accounts can subscribe; you are signed in as{" "}
              {account.role}.
            </p>
          ) : (
            <p className={styles.muted}>
              <Link to="/login">Sign in</Link> or{" "}
              <Link to="/register">create an account</Link> to subscribe.
            </p>
          )}
          {errors && (
            <ul className={styles.errorList}>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          )}
          <ul className={styles.policyList}>
            {[offer.registration_policy, offer.refund_policy]
              .filter(Boolean)
              .map((policy) => (
                <li key={policy.kind}>
                  <Link to={policy.url}>{policy.label} policy</Link> —
                  effective {formatDate(policy.effective_at)}
                </li>
              ))}
          </ul>
        </section>
      )}
    </main>
  );
}

export default Subscribe;
