"""Qualified assessment numbers fixed by 6.01.2 of the 2026 Standards.

The question minimums and their chart live in `question_minimums.py`
alongside the review-question minimums.
"""

from decimal import Decimal

# 6.01.2: "a cumulative minimum passing grade of at least 70 percent before
# issuing CPE credit for the course."
PASSING_PCT = Decimal("70")

# 6.01.2: the assessment "must measure a representative number of the
# learning objectives for the program", which is "75 percent or more". (The
# below-75 branch exists only for randomized test banks, which superCPE
# does not use.)
OBJECTIVE_COVERAGE_PCT = Decimal("75")

# 6.01.2: "The number of re-takes a participant is permitted to take is at
# the sponsor's discretion." A policy choice, not a Standards requirement.
# `None` is unlimited (ours, decided 2026-09-12: a participant who paid
# never pays again and is never locked out of the assessment); an integer
# is the number of re-takes after the first sitting, per enrollment (010's
# finite policy, kept working and tested under a monkeypatched value).
# Every attempt is retained whatever the value, preview attempts are never
# counted, and 011's `retake_policy_text()` renders whichever it is so the
# published policy cannot disagree with the code.
RETAKES_ALLOWED: int | None = None
