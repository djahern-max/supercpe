"""Per-jurisdiction credit policy fixed points (020).

7.01: "rules and regulations of state boards of accountancy may differ on
acceptable increments of CPE credit", and sponsors "may round down (but
not up) CPE credits awarded ... to the nearest one-fifth, one-half, or
whole credit increment". The three increments below are the Standard's
own list; `unknown` is superCPE's honest default for a board nobody has
verified yet. 7.01 closes with "The CPA claiming the CPE credits should
refer to the respective state board requirements" — the final-authority
sentence exists so the hint never reads as speaking for a board.
"""

from decimal import Decimal

# 7.01: the acceptable rounding increments a board may require, as the
# step each one rounds down to. `unknown` maps to no step: an unverified
# row is never displayed, let alone computed with.
CREDIT_INCREMENT_STEPS: dict[str, Decimal | None] = {
    "one_fifth": Decimal("0.2"),
    "one_half": Decimal("0.5"),
    "whole": Decimal("1.0"),
    "unknown": None,
}

CREDIT_INCREMENTS = tuple(CREDIT_INCREMENT_STEPS)

# superCPE's re-verification cadence, not NASBA's: a board rule read more
# than a year ago gets an admin-only staleness nudge (OPERATIONS.md,
# "Jurisdiction policies (020)").
VERIFIED_STALE_MONTHS = 12

# Shown verbatim, untruncatable, under every jurisdiction hint (7.01).
FINAL_AUTHORITY_SENTENCE = (
    "Boards of accountancy have final authority on the acceptance of CPE "
    "credits. Confirm the rules with your board."
)
