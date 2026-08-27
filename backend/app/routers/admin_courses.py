from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models.course import Course
from app.models.lesson_package import LessonPackage
from app.schemas.course import (
    AdminQuestion,
    AttachRequest,
    CourseCreate,
    CourseCreditAdmin,
    CourseDetailAdmin,
    CourseLessonItem,
    CourseSummaryAdmin,
    CourseUpdate,
    CreditLessonRowOut,
    MoveRequest,
    ObjectiveGroup,
    QuestionGroup,
    ReadinessFinding,
    ReviewCountsOut,
    UpdateVersionRequest,
)
from app.schemas.package import ValidationErrors
from app.services import courses, credit, readiness
from app.services import questions as questions_service
from app.services.courses import CourseRuleViolation

router = APIRouter(prefix="/admin/courses", dependencies=[Depends(require_admin)])


def _get_course_or_404(db: Session, course_code: str) -> Course:
    course = courses.get_course(db, course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _violation_response(violation: CourseRuleViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": violation.errors})


def _lesson_items(db: Session, course: Course) -> list[CourseLessonItem]:
    items = []
    for lesson in sorted(course.lessons, key=lambda cl: cl.position):
        latest = db.scalar(
            select(LessonPackage)
            .where(LessonPackage.lesson_id == lesson.package.lesson_id)
            .order_by(LessonPackage.version.desc())
            .limit(1)
        )
        has_newer = latest is not None and latest.version > lesson.package.version
        items.append(
            CourseLessonItem(
                package_id=lesson.package_id,
                lesson_id=lesson.package.lesson_id,
                version=lesson.package.version,
                position=lesson.position,
                title=lesson.package.title,
                duration_seconds=lesson.package.duration_seconds,
                newer_package_id=latest.id if has_newer else None,
                newer_version=latest.version if has_newer else None,
            )
        )
    return items


def _credit_panel(course: Course) -> CourseCreditAdmin:
    breakdown = credit.from_stored(course)
    return CourseCreditAdmin(
        is_stale=credit.is_stale(course),
        stale_reason=credit.stale_reason(course),
        computed_at=course.credit_computed_at,
        formula_version=course.credit_formula_version,
        award=str(breakdown.award) if breakdown else None,
        raw_minutes=str(breakdown.raw_minutes) if breakdown else None,
        raw_credit=str(breakdown.raw_credit) if breakdown else None,
        word_count=breakdown.word_count if breakdown else None,
        av_seconds=breakdown.av_seconds if breakdown else None,
        question_count=breakdown.question_count if breakdown else None,
        word_minutes=str(breakdown.word_minutes) if breakdown else None,
        av_minutes=str(breakdown.av_minutes) if breakdown else None,
        question_minutes=str(breakdown.question_minutes) if breakdown else None,
        rows=[
            CreditLessonRowOut(**vars(row)) for row in breakdown.rows
        ]
        if breakdown
        else [],
        as_text=credit.as_text(breakdown) if breakdown else None,
    )


def _admin_question(question) -> AdminQuestion:
    return AdminQuestion(
        question_key=question.question_key,
        kind=question.kind,
        after_block=question.after_block,
        position=question.position,
        stem=question.stem,
        choice_count=len(question.choices),
        counts_toward_minimum=questions_service.counts_toward_minimum(question),
    )


def _question_groups(db: Session, course: Course) -> list[QuestionGroup]:
    groups = []
    for lesson in sorted(course.lessons, key=lambda cl: cl.position):
        questions = questions_service.for_package(db, lesson.package_id)
        groups.append(
            QuestionGroup(
                lesson_id=lesson.package.lesson_id,
                package_id=lesson.package_id,
                position=lesson.position,
                review=[
                    _admin_question(q) for q in questions if q.kind == "review"
                ],
                assessment=[
                    _admin_question(q) for q in questions if q.kind == "assessment"
                ],
            )
        )
    return groups


def _detail(db: Session, course: Course) -> CourseDetailAdmin:
    return CourseDetailAdmin(
        id=course.id,
        course_code=course.course_code,
        title=course.title,
        description=course.description,
        field_of_study=course.field_of_study,
        knowledge_level=course.knowledge_level,
        prerequisites=course.prerequisites,
        advance_preparation=course.advance_preparation,
        status=course.status,
        content_updated_at=course.content_updated_at,
        created_at=course.created_at,
        updated_at=course.updated_at,
        lessons=_lesson_items(db, course),
        objectives=[
            ObjectiveGroup(**group) for group in courses.course_objectives(course)
        ],
        credit=_credit_panel(course),
        questions=_question_groups(db, course),
        readiness=[
            ReadinessFinding(**vars(finding))
            for finding in readiness.check(db, course)
        ],
        review_counts=ReviewCountsOut(
            **vars(readiness.review_counts(db, course))
        ),
    )


@router.post(
    "",
    response_model=CourseDetailAdmin,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    try:
        course = courses.create_course(
            db, payload.course_code, payload.title, payload.description
        )
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.get("", response_model=list[CourseSummaryAdmin])
def list_courses(db: Session = Depends(get_db)):
    return [
        CourseSummaryAdmin(
            id=course.id,
            course_code=course.course_code,
            title=course.title,
            status=course.status,
            lesson_count=len(course.lessons),
            content_updated_at=course.content_updated_at,
            credit_award=(
                str(course.credit_award)
                if course.credit_award is not None
                else None
            ),
            credit_is_stale=credit.is_stale(course),
        )
        for course in courses.list_courses(db)
    ]


@router.get("/{course_code}", response_model=CourseDetailAdmin)
def get_course(course_code: str, db: Session = Depends(get_db)):
    return _detail(db, _get_course_or_404(db, course_code))


@router.patch(
    "/{course_code}",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def update_course(
    course_code: str, payload: CourseUpdate, db: Session = Depends(get_db)
):
    course = _get_course_or_404(db, course_code)
    course = courses.update_course(db, course, payload.title, payload.description)
    return _detail(db, course)


@router.delete("/{course_code}", status_code=204, responses={422: {"model": ValidationErrors}})
def delete_course(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    try:
        courses.delete_course(db, course)
    except CourseRuleViolation as violation:
        return _violation_response(violation)


@router.post("/{course_code}/credit/recompute", response_model=CourseDetailAdmin)
def recompute_credit(course_code: str, db: Session = Depends(get_db)):
    """Explicit recompute for the stale cases mutations cannot reach: a
    formula-version bump, or defense in depth."""
    course = _get_course_or_404(db, course_code)
    credit.store(db, course.id)
    db.refresh(course)
    return _detail(db, course)


@router.post(
    "/{course_code}/lessons",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def attach_package(
    course_code: str, payload: AttachRequest, db: Session = Depends(get_db)
):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.attach_package(db, course, payload.package_id, payload.position)
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.delete(
    "/{course_code}/lessons/{package_id}",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def detach_package(
    course_code: str, package_id: int, db: Session = Depends(get_db)
):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.detach_package(db, course, package_id)
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.post(
    "/{course_code}/lessons/{package_id}/move",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def move_lesson(
    course_code: str,
    package_id: int,
    payload: MoveRequest,
    db: Session = Depends(get_db),
):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.move_lesson(db, course, package_id, payload.direction)
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.post(
    "/{course_code}/lessons/{package_id}/update-version",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def update_version(
    course_code: str,
    package_id: int,
    payload: UpdateVersionRequest,
    db: Session = Depends(get_db),
):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.update_version(
            db, course, package_id, payload.new_package_id
        )
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)
