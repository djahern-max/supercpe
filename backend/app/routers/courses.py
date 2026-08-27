"""Public catalog. Serves published courses only, with the full 8.01
disclosure payload; while nothing is published it correctly serves nothing.
No auth: this is what a potential participant reads before enrolling."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.course import Course
from app.schemas.course import (
    CoursePublicDetail,
    CoursePublicSummary,
    PublicLesson,
    PublicObjectiveGroup,
)
from app.services import courses, credit

router = APIRouter(prefix="/courses")


def _summary_fields(course: Course) -> dict:
    ordered = sorted(course.lessons, key=lambda cl: cl.position)
    recommended_credit, credit_basis = credit.public_credit(course)
    return {
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
    }


@router.get("", response_model=list[CoursePublicSummary])
def list_courses(db: Session = Depends(get_db)):
    return [
        CoursePublicSummary(**_summary_fields(course))
        for course in courses.list_published(db)
    ]


@router.get("/{course_code}", response_model=CoursePublicDetail)
def get_course(course_code: str, db: Session = Depends(get_db)):
    course = courses.get_published(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    ordered = sorted(course.lessons, key=lambda cl: cl.position)
    return CoursePublicDetail(
        **_summary_fields(course),
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
    )
