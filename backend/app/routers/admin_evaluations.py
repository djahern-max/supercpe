"""Admin views of evaluation results (4.04) and the 4.04.2 review log.

The summary page names the developer of record: 4.04.2 says sponsors
"should inform developers" of results, and until email exists (018) the
named developer beside the summary is how the admin knows who to tell;
`informed_developer` on a review is their attestation that they did.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.models.course import Course
from app.models.evaluation import EvaluationReview
from app.schemas.evaluation import (
    AdminEvaluationsOut,
    EvaluationReviewCreate,
    EvaluationReviewOut,
    EvaluationRowOut,
)
from app.services import courses
from app.services import evaluations as evaluations_service

router = APIRouter(
    prefix="/admin/courses", dependencies=[Depends(require_role("admin"))]
)


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/{course_code}/evaluations", response_model=AdminEvaluationsOut)
def list_evaluations(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    return AdminEvaluationsOut(
        course_code=course.course_code,
        developer_name=course.developer.name if course.developer else None,
        summary=evaluations_service.summary(db, course),
        rows=[
            EvaluationRowOut(
                id=row.id,
                submitted_at=row.submitted_at,
                objectives_met=row.objectives_met,
                prerequisites_appropriate=row.prerequisites_appropriate,
                materials_relevant=row.materials_relevant,
                time_appropriate=row.time_appropriate,
                instructors_effective=row.instructors_effective,
                comments=row.comments,
            )
            for row in evaluations_service.for_course(db, course)
        ],
    )


def _review_out(review: EvaluationReview) -> EvaluationReviewOut:
    return EvaluationReviewOut(
        id=review.id,
        reviewed_at=review.reviewed_at,
        reviewed_by_email=review.reviewed_by.email,
        note=review.note,
        informed_developer=review.informed_developer,
        summary_snapshot=review.summary_snapshot,
    )


@router.get(
    "/{course_code}/evaluation-reviews",
    response_model=list[EvaluationReviewOut],
)
def list_evaluation_reviews(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    return [
        _review_out(review)
        for review in evaluations_service.reviews_for_course(db, course)
    ]


@router.post(
    "/{course_code}/evaluation-reviews",
    response_model=EvaluationReviewOut,
    status_code=201,
)
def record_evaluation_review(
    course_code: str,
    payload: EvaluationReviewCreate,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("admin")),
):
    course = _get_course_or_404(db, course_code)
    review = evaluations_service.record_review(
        db, course, account, payload.note, payload.informed_developer
    )
    return _review_out(review)
