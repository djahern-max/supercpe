"""The development and review chain on a course (4.01, 4.01.1, 4.02).

Setting the developer, the review cycle, or recording a review is not a
content change: none of it calls `touch`, so it is allowed on a published
course and cannot make the review stale. A review is immutable once
recorded; corrections are new reviews.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.constants.review_cycle import REVIEW_CYCLE_DAYS
from app.models.account import Account
from app.models.course import Course
from app.models.review import CourseReview
from app.models.sme import SubjectMatterExpert
from app.services.courses import CourseRuleViolation


def _get_sme(db: Session, sme_id: int) -> SubjectMatterExpert:
    sme = db.get(SubjectMatterExpert, sme_id)
    if sme is None:
        raise CourseRuleViolation([f"subject matter expert {sme_id} does not exist"])
    return sme


def set_developer(
    db: Session, course: Course, sme_id: int, used_technology: bool
) -> Course:
    _get_sme(db, sme_id)
    course.developer_id = sme_id
    course.developer_used_technology = used_technology
    db.commit()
    return course


def set_review_cycle(db: Session, course: Course, review_cycle: str) -> Course:
    course.review_cycle = review_cycle
    db.commit()
    return course


def record_review(
    db: Session,
    course: Course,
    reviewer_id: int,
    reviewed_at: date,
    decision: str,
    notes: str = "",
    impractical_basis: str | None = None,
    *,
    recorded_by: Account,
) -> CourseReview:
    _get_sme(db, reviewer_id)
    # recorded_by snapshots the account's email at the time, so the record
    # reads the same after a display-name change; pre-009 rows carry the
    # literal "admin" and a null account.
    review = CourseReview(
        course_id=course.id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        content_updated_at_reviewed=course.content_updated_at,
        decision=decision,
        notes=notes,
        impractical_basis=impractical_basis,
        recorded_by=recorded_by.email,
        recorded_by_account_id=recorded_by.id,
    )
    course.reviews.append(review)
    db.commit()
    return review


def sorted_reviews(course: Course) -> list[CourseReview]:
    """Newest first, by review date then recording order."""
    return sorted(course.reviews, key=lambda r: (r.reviewed_at, r.id), reverse=True)


def is_superseded(course: Course, review: CourseReview) -> bool:
    """The content changed after this review was recorded, so it no longer
    reviews what the course now says (4.02: review again after each
    significant revision)."""
    return review.content_updated_at_reviewed < course.content_updated_at


def current_review(course: Course) -> CourseReview | None:
    """The latest approved review of the content as it stands now. None if
    no review was ever approved or the content has changed since."""
    for review in sorted_reviews(course):
        if review.decision == "approved" and not is_superseded(course, review):
            return review
    return None


def review_due_at(course: Course) -> date | None:
    """When 4.01 next requires a review, from the current review's date and
    the course's cycle. None while there is no current review (a block
    finding covers that case)."""
    review = current_review(course)
    if review is None:
        return None
    return review.reviewed_at + timedelta(days=REVIEW_CYCLE_DAYS[course.review_cycle])


def last_documented_date(course: Course) -> date | None:
    """The 4.01 disclosure: the most recent publication, revision, or
    review date — the greater of `published_at` and the latest review's
    `reviewed_at`."""
    dates = [r.reviewed_at for r in course.reviews]
    if course.published_at is not None:
        dates.append(course.published_at.date())
    return max(dates) if dates else None
