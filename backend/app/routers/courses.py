"""Public catalog. Serves published courses only, with the full 8.01
disclosure payload; while nothing is published it correctly serves nothing.
This is what a potential participant reads before enrolling — public while
the site is open; while it is coming_soon, only sessions get through and
everyone else sees 404 (require_site_open_or_session)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_site_open_or_session
from app.constants.certificate import PROGRAM_TYPE
from app.db import get_db
from app.models.course import Course
from app.schemas.course import (
    CoursePublicDetail,
    CoursePublicSummary,
    PolicyLink,
    PublicLesson,
    PublicObjectiveGroup,
    PublicOutlineLesson,
    PublicPerson,
)
from app.services import courses, credit, development
from app.services import policies as policies_service

router = APIRouter(
    prefix="/courses",
    dependencies=[Depends(require_site_open_or_session)],
)


def _person(sme) -> PublicPerson | None:
    """Name and credentials only — never a license number (those live in
    the 9.02.2(4) record, not the announcement)."""
    if sme is None:
        return None
    return PublicPerson(name=sme.name, credentials=sme.credentials)


def _renderable(course: Course) -> bool:
    """A course whose stored credit is stale cannot disclose 8.01 item 3,
    and a page missing an item is partial disclosure — so the payload
    refuses to render the course at all. Possible only in dev: a stale
    published course fails the publish gate, and production starts
    empty."""
    return not credit.is_stale(course)


def _summary_fields(course: Course) -> dict:
    ordered = sorted(course.lessons, key=lambda cl: cl.position)
    recommended_credit, credit_basis = credit.public_credit(course)
    current_review = development.current_review(course)
    return {
        "program_type": PROGRAM_TYPE,
        "developed_by": _person(course.developer),
        "reviewed_by": _person(current_review.reviewer if current_review else None),
        "last_reviewed": current_review.reviewed_at if current_review else None,
        "last_documented_date": development.last_documented_date(course),
        "recommended_credit": recommended_credit,
        "credit_basis": credit_basis,
        "course_code": course.course_code,
        "title": course.title,
        "description": course.description,
        "field_of_study": course.field_of_study,
        "knowledge_level": course.knowledge_level,
        "prerequisites": course.prerequisites,
        "advance_preparation": course.advance_preparation,
        "lesson_count": len(ordered),
        "total_duration_seconds": sum(
            cl.package.duration_seconds for cl in ordered
        ),
        # 018: what the Registration section and catalog card render as
        # dollars.
        "price_cents": course.price_cents,
    }


@router.get("", response_model=list[CoursePublicSummary])
def list_courses(db: Session = Depends(get_db)):
    return [
        CoursePublicSummary(**_summary_fields(course))
        for course in courses.list_published(db)
        if _renderable(course)
    ]


def _policy_link(db: Session, kind: str) -> PolicyLink | None:
    version = policies_service.current_version(db, kind)
    if version is None:
        return None
    return PolicyLink(
        kind=kind,
        label=policies_service.KIND_LABELS[kind],
        url=f"/policies#{kind}",
        effective_at=version.effective_at,
    )


def public_detail(db: Session, course) -> CoursePublicDetail:
    """The full 8.01 payload for one course — also what the audit bundle
    stores as 6-descriptive/course.json, so the bundle and the page can
    never disagree."""
    ordered = sorted(course.lessons, key=lambda cl: cl.position)
    title_of = {cl.package.lesson_id: cl.package.title for cl in ordered}
    return CoursePublicDetail(
        **_summary_fields(course),
        registration_policy=_policy_link(db, "registration"),
        refund_policy=_policy_link(db, "refund"),
        complaint_policy=_policy_link(db, "complaint"),
        sponsor_statement=policies_service.sponsor_statement(db),
        objectives=[
            PublicObjectiveGroup(
                lesson_id=group["lesson_id"],
                position=group["position"],
                objectives=group["objectives"],
            )
            for group in courses.course_objectives(course)
        ],
        lessons=[
            PublicLesson(
                lesson_id=cl.package.lesson_id,
                position=cl.position,
                title=cl.package.title,
                duration_seconds=cl.package.duration_seconds,
            )
            for cl in ordered
        ],
        outline=[
            PublicOutlineLesson(
                lesson_id=group["lesson_id"],
                position=group["position"],
                title=title_of[group["lesson_id"]],
                objectives=group["objectives"],
            )
            for group in courses.course_objectives(course)
        ],
    )


@router.get("/{course_code}", response_model=CoursePublicDetail)
def get_course(course_code: str, db: Session = Depends(get_db)):
    course = courses.get_published(db, course_code)
    if course is None or not _renderable(course):
        raise HTTPException(status_code=404, detail="Course not found")
    return public_detail(db, course)
