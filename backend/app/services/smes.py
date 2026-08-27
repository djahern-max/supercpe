"""Subject matter expert records (4.01.1, 4.02.1, 9.02.2(4)).

An SME is a person who was qualified on a date, not a login; nothing here
touches accounts. Deletion is refused while the SME is named on any course
or review, because 9.02.2(4) requires the name and credentials to be
retained with the record they support.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.review import CourseReview
from app.models.sme import SubjectMatterExpert
from app.services.courses import CourseRuleViolation


def list_smes(db: Session) -> list[SubjectMatterExpert]:
    return list(
        db.scalars(select(SubjectMatterExpert).order_by(SubjectMatterExpert.name))
    )


def get_sme(db: Session, sme_id: int) -> SubjectMatterExpert | None:
    return db.get(SubjectMatterExpert, sme_id)


def create_sme(db: Session, **fields) -> SubjectMatterExpert:
    sme = SubjectMatterExpert(**fields)
    db.add(sme)
    db.commit()
    return sme


def update_sme(
    db: Session, sme: SubjectMatterExpert, **fields
) -> SubjectMatterExpert:
    for name, value in fields.items():
        if value is not None:
            setattr(sme, name, value)
    db.commit()
    return sme


def delete_sme(db: Session, sme: SubjectMatterExpert) -> None:
    developed = list(
        db.scalars(
            select(Course.course_code).where(Course.developer_id == sme.id)
        )
    )
    reviewed = list(
        db.scalars(
            select(Course.course_code)
            .join(CourseReview, CourseReview.course_id == Course.id)
            .where(CourseReview.reviewer_id == sme.id)
            .distinct()
        )
    )
    errors = []
    if developed:
        errors.append(
            f"{sme.name} is the developer of record on: {', '.join(developed)}"
        )
    if reviewed:
        errors.append(
            f"{sme.name} is the reviewer on recorded reviews of: "
            f"{', '.join(reviewed)}; 9.02.2(4) retains the reviewer's name "
            "with the review"
        )
    if errors:
        raise CourseRuleViolation(errors)
    db.delete(sme)
    db.commit()
