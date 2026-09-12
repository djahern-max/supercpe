import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { listSubscriptions, voidEnrollment } from "../../api/admin";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import styles from "../AdminPayments/AdminPayments.module.css";

function stripeUrl(row) {
  const base =
    row.livemode === false
      ? "https://dashboard.stripe.com/test"
      : "https://dashboard.stripe.com";
  return `${base}/subscriptions/${row.stripe_subscription_id}`;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : "—";
}

// 029: the Billing paper trail. No actions beyond 018's enrollment void,
// offered beside each active enrollment of a refunded subscription.
// Refunds and cancellations happen in the Stripe dashboard (the refund
// runbook); the webhook syncs what Stripe reports. The two flags are the
// queue of refund-policy decisions awaiting an admin — not bugs.
function AdminSubscriptions() {
  const { refresh: refreshSession } = useSession();
  const [rows, setRows] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [errors, setErrors] = useState(null);

  const refresh = useCallback(() => {
    listSubscriptions()
      .then((data) => {
        setRows(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setLoadError("Could not load subscriptions. Is the backend running?");
      });
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleVoid = async (row, enrollment) => {
    const sure = window.confirm(
      `Void enrollment ${enrollment.enrollment_id} (${enrollment.course_code}) ` +
        `for ${row.email}? Their access to the course ends immediately. ` +
        "This follows the published refund policy and is logged."
    );
    if (!sure) return;
    setErrors(null);
    try {
      await voidEnrollment(enrollment.enrollment_id);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) refreshSession();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["The void failed. Try again."]);
    }
  };

  const stillCurrent = (rows ?? []).filter(
    (r) => r.refunded_with_current_subscription
  );
  const stillEnrolled = (rows ?? []).filter(
    (r) => r.refunded_with_active_enrollments
  );

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Subscriptions</h1>
      <p className={styles.muted}>
        Every subscription Stripe Billing reported, with its invoices.
        Financial records — never deleted. Refunds and cancellations are
        done in the Stripe dashboard; whether a refund also ends access to
        the courses started under it is the refund policy's question,
        answered here with Void.
      </p>
      {loadError && <div className={styles.errorPanel}>{loadError}</div>}
      {errors && <div className={styles.errorPanel}>{errors.join(" ")}</div>}
      {stillCurrent.length > 0 && (
        <div className={styles.flagPanel}>
          {stillCurrent.length === 1
            ? "1 refunded subscription is still current."
            : `${stillCurrent.length} refunded subscriptions are still current.`}{" "}
          Cancel it in the Stripe dashboard; the status syncs here.
        </div>
      )}
      {stillEnrolled.length > 0 && (
        <div className={styles.flagPanel}>
          {stillEnrolled.length === 1
            ? "1 refunded subscription still has active enrollments."
            : `${stillEnrolled.length} refunded subscriptions still have active enrollments.`}{" "}
          Decide per the refund policy whether access ends.
        </div>
      )}
      {rows !== null && rows.length === 0 && (
        <p className={styles.muted}>No subscriptions yet.</p>
      )}
      {rows !== null && rows.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Started</th>
                <th>Account</th>
                <th>Status</th>
                <th>Period</th>
                <th>Credit</th>
                <th>Cancels at period end</th>
                <th>Stripe</th>
                <th>Invoices</th>
                <th>Active enrollments</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={
                    row.refunded_with_current_subscription ||
                    row.refunded_with_active_enrollments
                      ? styles.flaggedRow
                      : undefined
                  }
                >
                  <td>{new Date(row.created_at).toLocaleString()}</td>
                  <td>{row.email}</td>
                  <td>
                    {row.status}
                    {row.current && " (current)"}
                  </td>
                  <td>
                    {formatDate(row.current_period_start)} –{" "}
                    {formatDate(row.current_period_end)}
                  </td>
                  <td>{formatUsd(row.credit_applied_cents)}</td>
                  <td>{row.cancel_at_period_end ? "yes" : "no"}</td>
                  <td className={styles.stripeIds}>
                    {row.stripe_subscription_id ? (
                      <a href={stripeUrl(row)} target="_blank" rel="noreferrer">
                        {row.stripe_subscription_id}
                      </a>
                    ) : (
                      "—"
                    )}
                    {row.livemode === false && (
                      <span
                        className={styles.testMarker}
                        title="A Stripe test-mode subscription, as Stripe reported it"
                      >
                        Test
                      </span>
                    )}
                  </td>
                  <td>
                    {row.invoices.length === 0
                      ? "—"
                      : row.invoices.map((invoice) => (
                          <div key={invoice.id}>
                            {formatUsd(invoice.amount_paid_cents)} · {invoice.status}
                            {invoice.period_end &&
                              ` · to ${formatDate(invoice.period_end)}`}
                          </div>
                        ))}
                  </td>
                  <td>
                    {row.active_enrollments.length === 0
                      ? "—"
                      : row.active_enrollments.map((enrollment) => (
                          <div key={enrollment.enrollment_id}>
                            #{enrollment.enrollment_id} {enrollment.course_code}{" "}
                            <button
                              className={styles.voidButton}
                              type="button"
                              onClick={() => handleVoid(row, enrollment)}
                            >
                              Void enrollment
                            </button>
                          </div>
                        ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

export default AdminSubscriptions;
