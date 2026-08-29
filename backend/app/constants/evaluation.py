"""Program evaluation facts (4.04, 4.04.1, 4.04.2 of the 2026 Standards).

4.04.1 fixes *what* an evaluation determines (the five elements below);
NASBA fixes no scale, no solicitation window, and no review interval. The
1–5 scale, the 30-day solicitation window, and the 90-day review interval
are superCPE's own choices — "periodically" (4.04.2) made concrete so it
can be reported — and can change without touching the Standard.
"""

SCALE_MIN = 1
SCALE_MAX = 5

# The 4.04.1 elements as they are asked, keyed by the `evaluations` column
# that stores each answer. Code-versioned here so the wording that was
# asked is quotable in the audit bundle. Item 5 (instructors) is never
# asked: self study has no instructors, and the column exists only so the
# record visibly answers it as not applicable.
PROMPTS = {
    "objectives_met": "Were the stated learning objectives met?",
    "prerequisites_appropriate": (
        "Were the stated prerequisite requirements appropriate and "
        "sufficient?"
    ),
    "materials_relevant": (
        "Were the program materials, including the qualified assessment, "
        "relevant, and did they contribute to achieving the learning "
        "objectives?"
    ),
    "time_appropriate": (
        "Was the time allotted to the learning activity appropriate?"
    ),
    "instructors_effective": (
        "Were individual instructors effective? (Not applicable: self "
        "study programs have no instructors.)"
    ),
}

# The elements a participant actually rates, in the order they are asked.
RATED_ELEMENTS = (
    "objectives_met",
    "prerequisites_appropriate",
    "materials_relevant",
    "time_appropriate",
)

# How long after completion the evaluation prompt keeps appearing. Ours,
# not NASBA's: 4.04.1 says solicited, not required, and a month is long
# enough to ask without nagging forever.
SOLICIT_UNTIL_DAYS = 30

# 4.04.2's "periodically review evaluation results", made concrete: an
# evaluation left unreviewed longer than this raises the
# `evaluation_review_due` warn finding. Ours, not NASBA's; reported, never
# enforced.
EVALUATION_REVIEW_DAYS = 90
