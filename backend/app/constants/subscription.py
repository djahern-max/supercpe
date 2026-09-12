"""Annual subscription numbers (029). None of these are NASBA's — they
are the sponsor's own ("ours") — but they are named here for the same
reason the Standards numbers are: an inline numeral cannot be found or
questioned. Money is integer cents; dollars exist only in rendering."""

# ours: the annual subscription price, in cents, as displayed. The amount
# actually charged is whatever Stripe's Price object says; preflight
# compares the two (`python -m app.cli preflight`) and refuses an open
# site on mismatch, so the page and the charge cannot disagree.
SUBSCRIPTION_PRICE_CENTS = 14900

# ours: the length of one subscription period, for display and tests.
# The schedule itself is Stripe's yearly interval on the Price; nothing
# here computes a renewal date — `current_period_end` is copied from
# Stripe, never derived from this number.
SUBSCRIPTION_PERIOD_DAYS = 365

# Stripe's own subscription statuses, stored exactly as reported (never
# mapped). The spec expects the first six from our configuration;
# `trialing` and `paused` cannot arise from it (no trials, no pause
# collection) but are Stripe's, and a CHECK that refused a status Stripe
# sent would 500 the webhook and make Stripe retry forever. None of the
# eight but `active` is ever current — see `services.subscriptions.current`.
SUBSCRIPTION_STATUSES = (
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
)

# Stripe's invoice statuses as this feature records them, plus `refunded`
# — which is superCPE's word for "the charge behind this invoice was
# refunded" (`charge.refunded`), since Stripe leaves the invoice `paid`.
SUBSCRIPTION_INVOICE_STATUSES = (
    "paid",
    "open",
    "void",
    "uncollectible",
    "refunded",
)
