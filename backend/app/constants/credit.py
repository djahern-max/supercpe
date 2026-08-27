"""Credit measurement numbers fixed by Section 7 of the 2026 Standards.

Every value here is one NASBA chose, not one superCPE chose. When the
Standards change a number, bump CREDIT_FORMULA_VERSION: every stored credit
computed under the old version becomes stale by comparison, no migration
needed.
"""

from decimal import Decimal

CREDIT_FORMULA_VERSION = "2026-7.02.6"

# 7.01: one 50-minute period equals one full CPE credit.
MINUTES_PER_CREDIT = 50

# 7.02.6: the word count is divided by 180, the average reading speed of
# adults, in words per minute.
WORDS_PER_MINUTE = 180

# 7.02.6: review questions, exercises, and qualified assessment questions
# are multiplied by 1.85, the estimated average completion time per question,
# in minutes.
MINUTES_PER_QUESTION = Decimal("1.85")

# 7.01(3)(i): self study credit may be awarded in one-fifth increments from
# the first one-fifth credit. 7.02.6: round down, never up.
CREDIT_INCREMENT = Decimal("0.2")

# 7.01(3)(i): the minimum initial self study award is one-fifth credit;
# below it no credit can be recommended.
MIN_AWARDABLE = Decimal("0.2")

# 8.01 item 3: the basis disclosed next to the recommended credit.
CREDIT_BASIS = "Word count formula, 2026 Standards 7.02.6"
