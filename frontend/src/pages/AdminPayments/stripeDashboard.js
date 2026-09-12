// 026: `livemode` is Stripe's own word on a payment row, recorded from
// the session and never inferred. A test transaction links into the
// sandbox dashboard, where its id actually resolves; a live row, or a
// row older than the column (null), links as it always did.
export function stripeDashboardUrl(payment) {
  const base =
    payment.livemode === false
      ? "https://dashboard.stripe.com/test"
      : "https://dashboard.stripe.com";
  return `${base}/payments/${payment.stripe_payment_intent_id}`;
}
