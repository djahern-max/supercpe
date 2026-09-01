"""What a content reviewer is signing when they approve a course (4.02).

4.02 requires review by a content reviewer other than the developer before
first presentation and after each significant revision. The decision is
already a dated record naming a licensed reviewer; these are the
statements that record puts their name to, shown above the sign-off form.

The text is versioned, not stored per review: `ATTESTATION_VERSION` moves
when the wording changes, so a future reader can tell which statements a
given sign-off date carried.

`for_course` adds the 023 lines for a course with text lessons. They are
the two judgments only a human reading the guide can make, and both are
places where the credit formula could otherwise be inflated silently:
whether a supplemental video adds learning or merely reads the text
(7.02.7), and whether excluded material was correctly kept out of the
counted body (7.02.5).
"""

ATTESTATION_VERSION = "2026-09-01"

BASE_LINES = (
    "I have reviewed the content of this course for technical accuracy "
    "and currency, and it is accurate and current as of the review date.",
    "The stated learning objectives, knowledge level, prerequisites, and "
    "advance preparation describe this course as it stands.",
    "The review questions and the qualified assessment measure the stated "
    "learning objectives.",
    "I did not develop this course.",
)

TEXT_LINES = (
    "The supplemental videos in this course constitute additional "
    "learning for the participant and are not narration of the text "
    "(7.02.7); their duration therefore belongs in the credit "
    "calculation alongside the word count.",
    "Material that 7.02.5 excludes from the word count — the course "
    "introduction and participant instructions, author biographies, the "
    "table of contents, the glossary, and appendixes of supplementary "
    "reference material — is in front matter, glossary, or appendix "
    "sections and not in the counted body.",
)


def for_course(has_text_lesson: bool) -> list[str]:
    """The statements this course's reviewer signs."""
    return list(BASE_LINES) + (list(TEXT_LINES) if has_text_lesson else [])
