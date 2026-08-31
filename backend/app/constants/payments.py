"""Checkout numbers (018). None of these are NASBA's — they are Stripe's
and superCPE's own — but they are named here for the same reason the
Standards numbers are: an inline numeral cannot be found or questioned."""

# The only currency superCPE sells in. Amounts are integer cents
# everywhere in code; dollars exist only in rendering.
PAYMENT_CURRENCY = "usd"

# How long a Stripe Checkout Session stays payable — Stripe's own default
# lifetime for a hosted Checkout page. A `pending` payment younger than
# this is a live session the participant can still finish, so checkout
# returns its URL instead of minting another; older than this it is
# abandoned and a new session is minted.
CHECKOUT_SESSION_LIFETIME_HOURS = 24
