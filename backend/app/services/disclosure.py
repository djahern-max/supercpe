"""8.01 disclosure completeness: the one named check of which items a
course cannot yet make available in advance.

8.01 (2026 Standards) requires sponsors whose courses are developed for
sale to make eleven items of information available in advance. Every item
maps to a stored fact; an item is missing when its fact is blank and
unusable when its source refuses (a stale 005 credit fails item 3 even
though a number exists). Two items are constants and can never fail: item
2 (`PROGRAM_TYPE`) and item 11 while it applies (`NASBA_SPONSOR_STATEMENT`
rendered through `services.policies.sponsor_statement`). Item 11 is
conditional by the Standard's own wording — "if an approved NASBA
sponsor" — so while `may_claim_registry` is false it is inapplicable and
this check does not count it.

Three refusals hang off `missing_items`:
- `courses.publish` refuses while any item is missing (a course that
  cannot disclose completely cannot be published);
- `readiness.launch_findings` blocks `coming_soon -> open` while no
  published course passes (opening onto an empty or non-compliant
  catalog is opening onto nothing);
- the admin course view lists the items for a published course that
  would now fail — possible only in dev, since the publish gate refuses
  first; flagged, never auto-unpublished.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.course import Course
from app.services import courses as courses_service
from app.services import credit
from app.services import policies as policies_service

# The eleven items as 8.01 numbers them (developed-for-sale list).
ITEM_NAMES = {
    1: "Learning objectives",
    2: "Type of formal learning program",
    3: "Recommended CPE credit and recommended field of study",
    4: "Prerequisites",
    5: "Program knowledge level",
    6: "Advance preparation",
    7: "Program description",
    8: "Course registration and attendance requirements",
    9: "Refund policy / cancellation policy",
    10: "Complaint resolution policy",
    11: "Official NASBA sponsor statement",
}

# Items 8-10 are the 8.01.1 policies, by kind.
POLICY_ITEMS = {8: "registration", 9: "refund", 10: "complaint"}


@dataclass
class DisclosureItem:
    """One 8.01 item the course cannot currently disclose."""

    number: int
    name: str
    reason: str


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def missing_items(db: Session, course: Course) -> list[DisclosureItem]:
    """Every applicable 8.01 item that is missing or unusable, in the
    Standard's numbering. Empty means the course discloses completely."""
    missing: list[DisclosureItem] = []

    def add(number: int, reason: str) -> None:
        missing.append(DisclosureItem(number, ITEM_NAMES[number], reason))

    # Item 1: objectives arrive with the lesson packages (3.01, 004).
    if not any(
        group["objectives"] for group in courses_service.course_objectives(course)
    ):
        add(1, "the course has no learning objectives; they arrive with the lesson packages")

    # Item 2 is PROGRAM_TYPE, a constant; it cannot be missing.

    # Item 3: usable exactly when public_credit serves a number — it
    # serves (None, None) while the stored credit is stale or below the
    # minimum awardable, and a number that cannot be served cannot be
    # disclosed.
    recommended_credit, _ = credit.public_credit(course)
    reasons = []
    if recommended_credit is None:
        if credit.is_stale(course):
            reasons.append(
                f"the stored credit is unusable ({credit.stale_reason(course)})"
            )
        else:
            reasons.append(
                "the credit award is below the minimum awardable; there is "
                "no credit to recommend"
            )
    if _blank(course.field_of_study):
        reasons.append("the course has no field of study")
    if reasons:
        add(3, "; ".join(reasons))

    # Items 4 and 6: 3.02.1 and 8.01.2 want "None" stated in so many
    # words when nothing is required — a stored "None" is a statement, a
    # blank is not.
    if _blank(course.prerequisites):
        add(4, 'prerequisites are blank; "None" is a stored statement (8.01.2), a blank is not')
    if _blank(course.knowledge_level):
        add(5, "the course has no program knowledge level")
    if _blank(course.advance_preparation):
        add(6, 'advance preparation is blank; "None" is a stored statement, a blank is not')
    if _blank(course.description):
        add(7, "the program description is blank")

    # Items 8-10: the 8.01.1 policies, "formalized, published, and made
    # available" — a kind with no current published version fails.
    for number, kind in POLICY_ITEMS.items():
        if policies_service.current_version(db, kind) is None:
            add(
                number,
                f"the {policies_service.KIND_LABELS[kind]} policy has no "
                "current published version (8.01.1)",
            )

    # Item 11 applies only "if an approved NASBA sponsor". While it
    # applies the statement is a gated constant and cannot be missing;
    # while it does not, the item is not counted.

    return missing
