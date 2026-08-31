"""Course assembly from ingested lesson packages.

A course's title and description are typed by the admin; everything else the
Standards require a participant to read is derived from the attached packages
and must agree across them (3.01.1, 3.02.1). Rule violations raise
`CourseRuleViolation` carrying the error strings for the router to wrap in a
422 `{"errors": [...]}`, the same response shape as package ingest.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.course import Course, CourseLesson
from app.models.enrollment import Enrollment
from app.models.lesson_package import LessonPackage
from app.services import credit

# The course-level facts copied from the packages, in the order refusal
# messages name them.
DERIVED_FIELDS = (
    "field_of_study",
    "knowledge_level",
    "prerequisites",
    "advance_preparation",
)


class CourseRuleViolation(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def touch(course: Course) -> None:
    """The one place content_updated_at is ever bumped. Every mutation a
    participant could observe goes through here; later features derive
    "credit is stale" and "review is stale" from this single column."""
    course.content_updated_at = datetime.now(timezone.utc)


def _refuse_if_published(course: Course) -> None:
    """A published course is immutable: every mutation that would call
    `touch` refuses here. Changing published content means unpublishing,
    editing, and reviewing again — 4.02 requires review after each
    significant revision, and the stale-review block enforces it on the way
    back to published."""
    if course.status == "published":
        raise CourseRuleViolation(
            [
                f"course {course.course_code} is published and its content "
                "is immutable; unpublish it first, then edit and record a "
                "new review (4.02 requires review after each significant "
                "revision)"
            ]
        )


def _recompute_credit(db: Session, course: Course) -> None:
    """Every mutation that goes through `touch` ends here, so an admin never
    sees a stale credit on a course they just edited; staleness exists for
    formula-version changes and defense in depth, not as a normal state.
    Must run after `touch`'s timestamp so the stored credit comes out
    fresh."""
    credit.store(db, course.id)
    db.refresh(course)


def get_course(db: Session, course_code: str) -> Course | None:
    return db.scalar(select(Course).where(Course.course_code == course_code))


def list_courses(db: Session) -> list[Course]:
    return list(db.scalars(select(Course).order_by(Course.course_code)))


def create_course(
    db: Session, course_code: str, title: str, description: str = ""
) -> Course:
    if get_course(db, course_code) is not None:
        raise CourseRuleViolation(
            [f'course_code "{course_code}" is already in use']
        )
    course = Course(course_code=course_code, title=title, description=description)
    db.add(course)
    db.commit()
    _recompute_credit(db, course)
    return course


def update_course(
    db: Session,
    course: Course,
    title: str | None = None,
    description: str | None = None,
) -> Course:
    wants_title = title is not None and title != course.title
    wants_description = description is not None and description != course.description
    if wants_title or wants_description:
        _refuse_if_published(course)
        if wants_title:
            course.title = title
        if wants_description:
            course.description = description
        touch(course)
        db.commit()
        _recompute_credit(db, course)
    return course


def delete_course(db: Session, course: Course) -> None:
    """Detaches the lessons (rows cascade), never deletes packages. A
    course with enrollments is never deleted, whatever its status: the
    enrollments, completions, and attempts hanging off it are 9.02
    records."""
    enrollment_count = db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.course_id == course.id)
    )
    if enrollment_count:
        raise CourseRuleViolation(
            [
                f"course {course.course_code} has {enrollment_count} "
                "enrollment(s); courses with enrollments are never deleted "
                "(9.02 retains their records)"
            ]
        )
    if course.status != "draft":
        raise CourseRuleViolation(
            [f"course {course.course_code} is {course.status}; only draft courses can be deleted"]
        )
    db.delete(course)
    db.commit()


def _ordered(course: Course) -> list[CourseLesson]:
    return sorted(course.lessons, key=lambda cl: cl.position)


def _copy_derived(course: Course, package: LessonPackage) -> None:
    for field in DERIVED_FIELDS:
        setattr(course, field, getattr(package, field))


def _check_agreement(course: Course, package: LessonPackage) -> None:
    errors = [
        f'{field}: course has "{getattr(course, field)}" but package '
        f'{package.lesson_id} v{package.version} has "{getattr(package, field)}"'
        for field in DERIVED_FIELDS
        if getattr(package, field) != getattr(course, field)
    ]
    if errors:
        raise CourseRuleViolation(errors)


def _check_course_code(course: Course, package: LessonPackage) -> None:
    if package.course_code is None:
        raise CourseRuleViolation(
            [
                f"package {package.lesson_id} v{package.version} has no "
                "course_code in its manifest; it was exported before the "
                "contract required one. Re-export it from video-tool."
            ]
        )
    if package.course_code != course.course_code:
        raise CourseRuleViolation(
            [
                f'manifest course_code "{package.course_code}" does not match '
                f'course "{course.course_code}"; the lesson was exported for '
                "a different course"
            ]
        )


def attach_package(
    db: Session, course: Course, package_id: int, position: int | None = None
) -> Course:
    _refuse_if_published(course)
    package = db.get(LessonPackage, package_id)
    if package is None:
        raise CourseRuleViolation([f"package {package_id} does not exist"])

    attached = db.scalar(
        select(CourseLesson).where(CourseLesson.package_id == package.id)
    )
    if attached is not None:
        raise CourseRuleViolation(
            [
                f"package {package.lesson_id} v{package.version} is already "
                f"attached to course {attached.course.course_code}"
            ]
        )

    same_lesson = next(
        (cl for cl in course.lessons if cl.package.lesson_id == package.lesson_id),
        None,
    )
    if same_lesson is not None:
        raise CourseRuleViolation(
            [
                f"lesson {package.lesson_id} is already attached as "
                f"v{same_lesson.package.version}; two versions of one lesson "
                "cannot both be attached. Use update-version to swap."
            ]
        )

    if course.lessons:
        _check_agreement(course, package)

    _check_course_code(course, package)

    if position is None:
        position = package.manifest_position
    if position is None:
        raise CourseRuleViolation(
            [
                f"package {package.lesson_id} v{package.version} has no "
                "position in its manifest and none was given"
            ]
        )
    holder = next((cl for cl in course.lessons if cl.position == position), None)
    if holder is not None:
        raise CourseRuleViolation(
            [
                f"position {position} is already taken by lesson "
                f"{holder.package.lesson_id}; detach it or reorder first"
            ]
        )

    course.lessons.append(CourseLesson(package_id=package.id, position=position))
    _copy_derived(course, package)
    touch(course)
    db.commit()
    _recompute_credit(db, course)
    return course


def detach_package(db: Session, course: Course, package_id: int) -> Course:
    _refuse_if_published(course)
    lesson = next(
        (cl for cl in course.lessons if cl.package_id == package_id), None
    )
    if lesson is None:
        raise CourseRuleViolation(
            [f"package {package_id} is not attached to course {course.course_code}"]
        )
    course.lessons.remove(lesson)
    if not course.lessons:
        # Nullable until the first lesson is attached; an empty course has
        # no lessons to derive from.
        for field in DERIVED_FIELDS:
            setattr(course, field, None)
    touch(course)
    db.commit()
    _recompute_credit(db, course)
    return course


def move_lesson(
    db: Session, course: Course, package_id: int, direction: str
) -> Course:
    _refuse_if_published(course)
    ordered = _ordered(course)
    index = next(
        (i for i, cl in enumerate(ordered) if cl.package_id == package_id), None
    )
    if index is None:
        raise CourseRuleViolation(
            [f"package {package_id} is not attached to course {course.course_code}"]
        )
    if direction == "up":
        if index == 0:
            raise CourseRuleViolation(["lesson is already first"])
        ordered[index], ordered[index - 1] = ordered[index - 1], ordered[index]
    else:
        if index == len(ordered) - 1:
            raise CourseRuleViolation(["lesson is already last"])
        ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]

    # Two-pass renumber: park every row above the occupied range first so the
    # (course_id, position) unique constraint never sees a collision, then
    # assign the dense final order.
    offset = max(cl.position for cl in ordered)
    for i, lesson in enumerate(ordered):
        lesson.position = offset + i + 1
    db.flush()
    for i, lesson in enumerate(ordered):
        lesson.position = i + 1
    touch(course)
    db.commit()
    _recompute_credit(db, course)
    return course


def update_version(
    db: Session, course: Course, package_id: int, new_package_id: int
) -> Course:
    _refuse_if_published(course)
    lesson = next(
        (cl for cl in course.lessons if cl.package_id == package_id), None
    )
    if lesson is None:
        raise CourseRuleViolation(
            [f"package {package_id} is not attached to course {course.course_code}"]
        )
    new = db.get(LessonPackage, new_package_id)
    if new is None:
        raise CourseRuleViolation([f"package {new_package_id} does not exist"])
    old = lesson.package
    if new.lesson_id != old.lesson_id:
        raise CourseRuleViolation(
            [
                f"package {new.lesson_id} v{new.version} is not a version of "
                f"lesson {old.lesson_id}"
            ]
        )
    if new.version <= old.version:
        raise CourseRuleViolation(
            [
                f"v{new.version} of {new.lesson_id} is not newer than the "
                f"attached v{old.version}"
            ]
        )
    _check_agreement(course, new)
    _check_course_code(course, new)

    lesson.package_id = new.id
    _copy_derived(course, new)
    touch(course)
    db.commit()
    _recompute_credit(db, course)
    return course


def course_objectives(course: Course) -> list[dict]:
    """The course's learning objectives, grouped by lesson in position order.
    Objective ids are unique only within a package, so consumers key on
    (package_id, objective_id)."""
    return [
        {
            "lesson_id": cl.package.lesson_id,
            "package_id": cl.package_id,
            "position": cl.position,
            "objectives": cl.package.manifest["learning_objectives"],
        }
        for cl in _ordered(course)
    ]


def list_published(db: Session) -> list[Course]:
    return list(
        db.scalars(
            select(Course)
            .where(Course.status == "published")
            .order_by(Course.course_code)
        )
    )


def get_published(db: Session, course_code: str) -> Course | None:
    course = get_course(db, course_code)
    if course is None or course.status != "published":
        return None
    return course


def publish(db: Session, course: Course) -> Course:
    """The publish gate: refuses with every block readiness finding and
    every missing 8.01 disclosure item at once — a course that cannot
    disclose completely cannot be published (016). Touches no content, so
    `content_updated_at` is unchanged and the review stays current."""
    # Deferred imports: readiness and disclosure import this module.
    from app.services import disclosure, readiness

    if course.status == "published":
        raise CourseRuleViolation(
            [f"course {course.course_code} is already published"]
        )
    blocks = [
        finding.message
        for finding in readiness.check(db, course)
        if finding.level == "block"
    ]
    blocks += [
        f"8.01 item {item.number} ({item.name}) cannot be disclosed: "
        f"{item.reason}"
        for item in disclosure.missing_items(db, course)
    ]
    if blocks:
        raise CourseRuleViolation(blocks)
    course.status = "published"
    course.published_at = datetime.now(timezone.utc)
    db.commit()
    return course


def unpublish(db: Session, course: Course) -> Course:
    if course.status != "published":
        raise CourseRuleViolation(
            [f"course {course.course_code} is not published"]
        )
    course.status = "draft"
    course.unpublished_at = datetime.now(timezone.utc)
    db.commit()
    return course
