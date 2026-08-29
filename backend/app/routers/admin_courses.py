from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.account import Account
from app.models.course import Course
from app.models.lesson_package import LessonPackage
from app.schemas.course import (
    AdminQuestion,
    AttachRequest,
    CourseCreate,
    CourseCreditAdmin,
    CourseDetailAdmin,
    CourseDevelopmentAdmin,
    CourseLessonItem,
    CourseReviewOut,
    CourseSummaryAdmin,
    CourseUpdate,
    CreditLessonRowOut,
    DeveloperRequest,
    MoveRequest,
    ObjectiveGroup,
    QuestionGroup,
    ReadinessFinding,
    ReviewCreate,
    ReviewCountsOut,
    ReviewCycleRequest,
    UpdateVersionRequest,
)
from app.schemas.package import ValidationErrors
from app.services import courses, credit, development, readiness
from app.services import questions as questions_service
from app.services.courses import CourseRuleViolation

router = APIRouter(
    prefix="/admin/courses", dependencies=[Depends(require_role("admin"))]
)


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


def _development_panel(course: Course) -> CourseDevelopmentAdmin:
    current = development.current_review(course)
    return CourseDevelopmentAdmin(
        developer_id=course.developer_id,
        developer_name=course.developer.name if course.developer else None,
        developer_credentials=(
            course.developer.credentials if course.developer else None
        ),
        developer_used_technology=course.developer_used_technology,
        review_cycle=course.review_cycle,
        published_at=course.published_at,
        unpublished_at=course.unpublished_at,
        review_due_at=development.review_due_at(course),
        last_documented_date=development.last_documented_date(course),
        reviews=[
            _review_out(course, review, current)
            for review in development.sorted_reviews(course)
        ],
    )


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
        development=_development_panel(course),
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
    try:
        course = courses.update_course(
            db, course, payload.title, payload.description
        )
    except CourseRuleViolation as violation:
        return _violation_response(violation)
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


@router.put(
    "/{course_code}/developer",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def set_developer(
    course_code: str, payload: DeveloperRequest, db: Session = Depends(get_db)
):
    course = _get_course_or_404(db, course_code)
    try:
        course = development.set_developer(
            db, course, payload.sme_id, payload.used_technology
        )
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.post(
    "/{course_code}/reviews",
    response_model=CourseDetailAdmin,
    status_code=201,
    responses={422: {"model": ValidationErrors}},
)
def record_review(
    course_code: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    account: Account = Depends(require_role("admin")),
):
    course = _get_course_or_404(db, course_code)
    try:
        development.record_review(
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
        return _violation_response(violation)
    return _detail(db, course)


@router.get("/{course_code}/reviews", response_model=list[CourseReviewOut])
def list_reviews(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    current = development.current_review(course)
    return [
        _review_out(course, review, current)
        for review in development.sorted_reviews(course)
    ]


@router.put("/{course_code}/review-cycle", response_model=CourseDetailAdmin)
def set_review_cycle(
    course_code: str, payload: ReviewCycleRequest, db: Session = Depends(get_db)
):
    course = _get_course_or_404(db, course_code)
    course = development.set_review_cycle(db, course, payload.review_cycle)
    return _detail(db, course)


@router.post(
    "/{course_code}/publish",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def publish_course(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.publish(db, course)
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)


@router.post(
    "/{course_code}/unpublish",
    response_model=CourseDetailAdmin,
    responses={422: {"model": ValidationErrors}},
)
def unpublish_course(course_code: str, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_code)
    try:
        course = courses.unpublish(db, course)
    except CourseRuleViolation as violation:
        return _violation_response(violation)
    return _detail(db, course)
