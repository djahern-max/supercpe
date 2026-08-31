import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { listPayments, voidEnrollment } from "../../api/admin";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import { formatUsd } from "../../constants/money";
import styles from "./AdminPayments.module.css";

// The money's paper trail (018). A refund never unwinds access by
// itself: the flagged rows are the queue of refund-policy decisions, and
// the guarded Void button is the "access ends" answer.
function AdminPayments() {
  const { refresh: refreshSession } = useSession();
  const [payments, setPayments] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [errors, setErrors] = useState(null);

  const refresh = useCallback(() => {
    listPayments()
      .then((data) => {
        setPayments(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setLoadError("Could not load payments. Is the backend running?");
      });
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleVoid = async (payment) => {
    const sure = window.confirm(
      `Void enrollment ${payment.enrollment_id} for ${payment.email}? ` +
        "Their access to the course ends immediately. This follows the " +
        "published refund policy and is logged."
    );
    if (!sure) return;
    setErrors(null);
    try {
      await voidEnrollment(payment.enrollment_id);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) refreshSession();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["The void failed. Try again."]);
    }
  };

  const flagged = (payments ?? []).filter(
    (p) => p.refunded_with_active_enrollment
  );

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Payments</h1>
      <p className={styles.muted}>
        Every checkout attempt that reached Stripe. Financial records —
        never deleted. Refunds are done in the Stripe dashboard; whether a
        refund also ends access is the refund policy's question, answered
        here with Void.
      </p>
      {loadError && <div className={styles.errorPanel}>{loadError}</div>}
      {errors && (
        <div className={styles.errorPanel}>{errors.join(" ")}</div>
      )}
      {flagged.length > 0 && (
        <div className={styles.flagPanel}>
          {flagged.length === 1
            ? "1 refunded payment still has an active enrollment."
            : `${flagged.length} refunded payments still have active enrollments.`}{" "}
          Decide per the refund policy whether access ends.
        </div>
      )}
      {payments !== null && payments.length === 0 && (
        <p className={styles.muted}>No payments yet.</p>
      )}
      {payments !== null && payments.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>When</th>
                <th>Account</th>
                <th>Course</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Enrollment</th>
                <th>Stripe</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payments.map((payment) => (
                <tr
                  key={payment.id}
                  className={
                    payment.refunded_with_active_enrollment
                      ? styles.flaggedRow
                      : undefined
                  }
                >
                  <td>{new Date(payment.created_at).toLocaleString()}</td>
                  <td>{payment.email}</td>
                  <td>{payment.course_code}</td>
                  <td>
                    {formatUsd(payment.amount_cents)}{" "}
                    {payment.currency !== "usd" &&
                      payment.currency.toUpperCase()}
                  </td>
                  <td>{payment.status}</td>
                  <td>
                    {payment.enrollment_id !== null
                      ? `#${payment.enrollment_id} (${payment.enrollment_status})`
                      : "—"}
                  </td>
                  <td className={styles.stripeIds}>
                    {payment.stripe_payment_intent_id ? (
                      <a
                        href={`https://dashboard.stripe.com/payments/${payment.stripe_payment_intent_id}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {payment.stripe_payment_intent_id}
                      </a>
                    ) : (
                      <span title={payment.stripe_checkout_session_id}>
                        {payment.stripe_checkout_session_id.slice(0, 18)}…
                      </span>
                    )}
                  </td>
                  <td>
                    {payment.refunded_with_active_enrollment && (
                      <button
                        className={styles.voidButton}
                        type="button"
                        onClick={() => handleVoid(payment)}
                      >
                        Void enrollment
                      </button>
                    )}
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

export default AdminPayments;
