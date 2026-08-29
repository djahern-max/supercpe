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
# the sponsor's discretion." The number of re-takes after the first sitting,
# per enrollment (010; 007 chose unlimited before an enrollment existed to
# count against). A policy choice, not a Standards requirement; every
# attempt is retained regardless, preview attempts are never counted, and
# feature 011 must disclose this policy on the course page.
RETAKES_ALLOWED = 3
