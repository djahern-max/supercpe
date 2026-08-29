"""The participant player's lesson payload and review-question grading.

A preview behind admin and reviewer sessions for now: reviewers must see
the program they sign off on (4.02). Feature 010 moves these routes behind
enrollment and adds persistence; the endpoints themselves are already the
participant ones. Grading is stateless (5.01.2.1 sets no passing rate on
review questions) and re-answering is allowed.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.lesson_package import LessonPackage
from app.schemas.package import ValidationErrors
from app.schemas.player import (
    PlayBlock,
    PlayChoice,
    PlayLesson,
    PlayQuestion,
    ReviewAnswer,
    ReviewResult,
)
from app.services import courses
from app.services import questions as questions_service
from app.storage import Storage, get_storage

router = APIRouter(
    prefix="/courses",
    dependencies=[Depends(require_role("admin", "reviewer"))],
)


def _get_lesson_package(
    db: Session, course_code: str, package_id: int
) -> LessonPackage:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    lesson = next(
        (cl for cl in course.lessons if cl.package_id == package_id), None
    )
    if lesson is None:
        raise HTTPException(
            status_code=404, detail="Lesson not attached to this course"
        )
    return lesson.package


@router.get("/{course_code}/lessons/{package_id}/play", response_model=PlayLesson)
def play_lesson(
    course_code: str,
    package_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    package = _get_lesson_package(db, course_code, package_id)
    return PlayLesson(
        lesson_id=package.lesson_id,
        title=package.title,
        video_url=storage.url(package.video_key),
        duration_seconds=package.duration_seconds,
        blocks=[PlayBlock(**block) for block in (package.blocks or [])],
        questions=[
            PlayQuestion(
                question_key=q.question_key,
                after_block=q.after_block,
                stem=q.stem,
                choices=[
                    PlayChoice(choice_key=c.choice_key, text=c.text)
                    for c in q.choices
                ],
            )
            for q in questions_service.for_package(db, package.id)
            if q.kind == "review"
        ],
    )


@router.post(
    "/{course_code}/lessons/{package_id}/review/{question_key}",
    response_model=ReviewResult,
    responses={422: {"model": ValidationErrors}},
)
def grade_review(
    course_code: str,
    package_id: int,
    question_key: str,
    answer: ReviewAnswer,
    db: Session = Depends(get_db),
):
    package = _get_lesson_package(db, course_code, package_id)
    question = questions_service.get_question(db, package.id, question_key)
    if question is None or question.kind != "review":
        raise HTTPException(status_code=404, detail="Review question not found")
    chosen = next(
        (c for c in question.choices if c.choice_key == answer.choice_key), None
    )
    if chosen is None:
        return JSONResponse(
            status_code=422,
            content={
                "errors": [
                    f'choice_key "{answer.choice_key}" is not a choice of '
                    f"question {question_key}"
                ]
            },
        )
    correct_choice = next(c for c in question.choices if c.is_correct)
    return ReviewResult(
        correct=chosen.is_correct,
        feedback=question.feedback,
        correct_choice_key=correct_choice.choice_key,
    )
