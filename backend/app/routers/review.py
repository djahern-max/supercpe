"""The reviewer surface (4.02): see courses, preview them, record a review
in the first person.

Reviewers cannot edit content, attach, publish, or manage anything; the
only write here is the review record, and recording one publishes nothing —
the 008 `reviewer_is_developer` and `cpa_participation` findings still gate
publish. Admins may use these routes too (an admin can still record a
review on a reviewer's behalf; the record then names the admin)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.constants import review_attestation
from app.constants.review_attestation import ATTESTATION_VERSION
from app.db import get_db
from app.models.account import Account
from app.models.course import Course
from app.schemas.course import CourseReviewOut, ReviewCreate
from app.schemas.package import ValidationErrors
from app.schemas.review import (
    ReviewCourseDetail,
    ReviewCourseSummary,
    ReviewLesson,
    ReviewSme,
)
from app.services import courses, development, smes
from app.services.courses import CourseRuleViolation

router = APIRouter(
    prefix="/review",
    dependencies=[Depends(require_role("reviewer", "admin"))],
)


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _standing(course: Course) -> tuple[str, object]:
    """One word on where the course's review stands, and the latest review
    date of any decision (the 4.01 disclosure logic)."""
    reviews = development.sorted_reviews(course)
    last_reviewed = reviews[0].reviewed_at if reviews else None
    if development.current_review(course) is not None:
        return "current", last_reviewed
    if any(r.decision == "approved" for r in reviews):
        return "superseded", last_reviewed
    return "none", last_reviewed


def _review_out(course: Course, review, current) -> CourseReviewOut:
    return CourseReviewOut(
        id=review.id,
        reviewer_id=review.reviewer_id,
        reviewer_name=review.reviewer.name,
        reviewer_credentials=review.reviewer.credentials,
        reviewed_at=review.reviewed_at,
        content_updated_at_reviewed=review.content_updated_at_reviewed,
        decision=review.decision,
        notes=review.notes,
        impractical_basis=review.impractical_basis,
        recorded_by=review.recorded_by,
        created_at=review.created_at,
        is_current=current is not None and review.id == current.id,
        is_superseded=development.is_superseded(course, review),
    )


@router.get("/courses", response_model=list[ReviewCourseSummary])
def list_courses(db: Session = Depends(get_db)):
    summaries = []
    for course in courses.list_courses(db):
        standing, last_reviewed = _standing(course)
        summaries.append(
            ReviewCourseSummary(
                course_code=course.course_code,
                title=course.title,
                status=course.status,
                review_standing=standing,
                last_reviewed=last_reviewed,
            )
        )
    return summaries


@router.get("/courses/{course_code}", response_model=ReviewCourseDetail)
def get_course(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    standing, last_reviewed = _standing(course)
    current = development.current_review(course)
    return ReviewCourseDetail(
        course_code=course.course_code,
        title=course.title,
        description=course.description,
        field_of_study=course.field_of_study,
        knowledge_level=course.knowledge_level,
        status=course.status,
        content_updated_at=course.content_updated_at,
        review_standing=standing,
        last_reviewed=last_reviewed,
        lessons=[
            ReviewLesson(
                package_id=lesson.package_id,
                position=lesson.position,
                title=lesson.package.title,
                kind=lesson.package.kind,
                duration_seconds=lesson.package.duration_seconds,
                word_count=lesson.package.word_count,
            )
            for lesson in sorted(course.lessons, key=lambda cl: cl.position)
        ],
        reviews=[
            _review_out(course, review, current)
            for review in development.sorted_reviews(course)
        ],
        smes=[
            ReviewSme(id=sme.id, name=sme.name, credentials=sme.credentials)
            for sme in smes.list_smes(db)
        ],
        # 4.02: what recording an approval puts this reviewer's name to.
        # A course with text lessons adds the two 023 judgments only a
        # human reading the guide can make — that the supplemental videos
        # add learning rather than narrate the text (7.02.7), and that
        # excluded material is out of the counted body (7.02.5). Both are
        # places the credit formula could otherwise be inflated without
        # anything in the code noticing.
        attestation_version=ATTESTATION_VERSION,
        attestation=review_attestation.for_course(
            any(cl.package.is_text for cl in course.lessons)
        ),
    )


@router.post(
    "/courses/{course_code}/reviews",
    response_model=CourseReviewOut,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def record_review(
    course_code: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("reviewer", "admin")),
):
    course = _get_course_or_404(db, course_code)
    try:
        review = development.record_review(
            db,
            course,
            payload.reviewer_id,
            payload.reviewed_at,
            payload.decision,
            payload.notes,
            payload.impractical_basis,
            recorded_by=account,
        )
    except CourseRuleViolation as violation:
        return JSONResponse(status_code=422, content={"errors": violation.errors})
    return _review_out(course, review, development.current_review(course))
