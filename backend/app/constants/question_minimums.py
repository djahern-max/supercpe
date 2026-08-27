"""Question minimums fixed by the 2026 Standards: review questions by
5.01.2.1, qualified assessment questions by 6.01.2.
"""

from decimal import Decimal

# 5.01.2.1: "At least three review questions or other content reinforcement
# tools with scored responses per CPE credit must be included."
REVIEW_PER_CREDIT = 3

# 5.01.2.1: "'True or false' questions do not count toward the number of
# required review questions per CPE credit." A two-choice question is a
# forced choice whatever its labels, so a review question counts only with
# at least this many choices.
COUNTING_MIN_CHOICES = 3

# The 5.01.2.1 chart, transcribed from the PDF: review questions required by
# the one-fifth credit measurement amount of the program, up to and including
# the first full credit.
REVIEW_MINIMUMS = {
    Decimal("0.2"): 0,
    Decimal("0.4"): 1,
    Decimal("0.5"): 2,
    Decimal("0.6"): 2,
    Decimal("0.8"): 3,
    Decimal("1.0"): 3,
}


def required_review_questions(credit: Decimal) -> int:
    """Review questions 5.01.2.1 requires for a program of this credit.

    Up to one credit, the answer is read straight from the chart. Above one
    credit, 5.01.2.1 says additional questions "are required based on the
    chart above" after the first full credit's minimum of three; decomposing
    the credit as `whole x 3 + chart[remainder]` (with the remainder taken in
    (0, 1] so the chart's own 1.0 row covers each completed credit) is
    superCPE's interpretation of that sentence, not a formula the paragraph
    states.

    True/false questions do not count toward these minimums; callers must
    count only questions with more than two choices.
    """
    if credit < min(REVIEW_MINIMUMS):
        return 0
    # Decompose so the remainder falls in (0, 1]: 1.0 -> 0 whole + 1.0,
    # 1.2 -> 1 whole + 0.2, 2.0 -> 1 whole + 1.0.
    whole = int(credit)
    remainder = credit - whole
    if remainder == 0:
        whole -= 1
        remainder = Decimal("1.0")
    if remainder not in REVIEW_MINIMUMS:
        raise ValueError(
            f"credit {credit} is not a 5.01.2.1 increment; its fractional "
            f"part must be one of {sorted(REVIEW_MINIMUMS)}"
        )
    return whole * REVIEW_PER_CREDIT + REVIEW_MINIMUMS[remainder]


# 6.01.2: "At least 5 questions and scored responses per CPE credit must be
# included on the qualified assessment."
ASSESSMENT_PER_CREDIT = 5

# 6.01.2: forced choice responses ("true or false", "yes or no") are not
# permissible on the qualified assessment, so a two-choice question can
# never appear on it; three choices is the floor.
MIN_CHOICES_ASSESSMENT = 3

# The 6.01.2 chart, transcribed from the PDF: assessment questions required
# by the one-fifth credit measurement amount of the program, up to and
# including the first full credit ("Next full credit: 5").
ASSESSMENT_MINIMUMS = {
    Decimal("0.2"): 2,
    Decimal("0.4"): 3,
    Decimal("0.5"): 4,
    Decimal("0.6"): 4,
    Decimal("0.8"): 5,
    Decimal("1.0"): 5,
}


def required_assessment_questions(credit: Decimal) -> int:
    """Assessment questions 6.01.2 requires for a program of this credit.

    Same decomposition as `required_review_questions`: read the chart up to
    one credit, then `whole x 5 + chart[remainder]` with the remainder in
    (0, 1]. Unlike the review case, 6.01.2 states its own worked examples —
    5 credits -> 25 and 5 1/2 credits -> 29 — and both fall out of this
    decomposition, so it is the paragraph's arithmetic, not an
    interpretation.
    """
    if credit < min(ASSESSMENT_MINIMUMS):
        return 0
    whole = int(credit)
    remainder = credit - whole
    if remainder == 0:
        whole -= 1
        remainder = Decimal("1.0")
    if remainder not in ASSESSMENT_MINIMUMS:
        raise ValueError(
            f"credit {credit} is not a 6.01.2 increment; its fractional "
            f"part must be one of {sorted(ASSESSMENT_MINIMUMS)}"
        )
    return whole * ASSESSMENT_PER_CREDIT + ASSESSMENT_MINIMUMS[remainder]
