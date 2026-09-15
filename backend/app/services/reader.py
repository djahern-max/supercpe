"""The participant reader: a text lesson served section by section (023).

The video player's shape, in the other medium. 5.01.2.1 requires review
questions "placed throughout the program in sufficient intervals to allow
the participant the opportunity to evaluate the material that needs to be
re-studied"; in a video that means pausing after a narrated block, and
here it means a body section that does not open until the question placed
after the preceding one has been answered.

Two rules this module exists to keep:

1. **The gate is server-side.** A locked section's markdown is not in the
   payload at all. A gate the browser could skip past would not be a gate.
2. **No answer key reaches the browser** — the same rule the player has
   kept since 006. Choices carry keys and text, never `is_correct`, and
   feedback is served only by the grading endpoint, only after an answer.

Reference material is never gated. Front matter, the glossary, and
appendixes are available from the first moment, for the same reason 7.02.5
excludes them from the word count: they are not required reading. The
supplemental videos are not gated either, and carry no seek lock — the
023 decision, recorded in docs/decisions/2026-09-01-text-first.md:
completion is verified by the qualified assessment (6.01.2), interval
placement is satisfied by the section gates, and the player's forward-seek
lock was always a sponsor design choice rather than a Standards
requirement. The video-only player keeps its own behavior.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.constants.package_kinds import ROLE_BODY, UNGATED_ROLES
from app.constants.storage import VIDEO_URL_SECONDS
from app.models.lesson_package import LessonPackage
from app.services import package_lifecycle
from app.services import questions as questions_service
from app.services.markdown import strip_html_comments
from app.storage import Storage


@dataclass
class ReaderQuestion:
    question_key: str
    after_section: str
    stem: str
    choices: list[dict]
    answered: bool


@dataclass
class ReaderMedia:
    media_key: str
    after_section: str
    url: str
    duration_seconds: int


@dataclass
class ReaderSection:
    section_key: str
    role: str
    title: str
    position: int
    word_count: int
    counted: bool
    locked: bool
    # None exactly when locked: the gate withholds the text, not just the
    # scroll position. Otherwise the shipped markdown with its authoring
    # annotations removed (035) — the stored row is untouched.
    markdown: str | None
    # Every review question placed after this section, in package order.
    # A list, not one key: nothing in 5.01.2.1 or the package contract
    # limits a section to a single question, and the fixture places two
    # after its first — all of them must be answered before the next body
    # section opens, or the gate would be satisfiable by answering
    # whichever one happened to be last.
    question_keys: list[str]


@dataclass
class ReaderLesson:
    lesson_id: str
    title: str
    kind: str
    word_count: int
    # 037: where the participant is. The course this lesson belongs to,
    # this lesson's place in it, and how far through the lesson's gated
    # sections they have got. Served, never parsed out of the URL by the
    # browser — the URL is a reading position, not a record (027).
    course_title: str
    lesson_position: int
    lesson_count: int
    # The gated sequence is the body sections and nothing else: front
    # matter, glossary, and appendixes are reference, ungated for the
    # same reason 7.02.5 keeps them out of the word count.
    section_count: int
    sections_completed: int
    sections: list[ReaderSection] = field(default_factory=list)
    media: list[ReaderMedia] = field(default_factory=list)
    questions: list[ReaderQuestion] = field(default_factory=list)
    # 038: set when the version's supplemental media files were purged
    # after retention; `media` is then empty and this sentence says why.
    media_removed: str | None = None


def build(
    db: Session,
    storage: Storage,
    package: LessonPackage,
    answered_keys: set[str] | None = None,
    *,
    gated: bool = True,
    course_title: str,
    lesson_position: int,
    lesson_count: int,
) -> ReaderLesson:
    """One text lesson's payload.

    `answered_keys` names the review questions this participant has
    already answered; `gated=False` is the admin and reviewer preview,
    which serves the whole guide unlocked. A reviewer has to read what
    they are signing (4.02), and no participant record exists to gate
    against.

    037: the course and the lesson's place in it are the caller's to
    supply, because they differ by surface — the participant's are the
    lessons pinned on their enrollment, the preview's are the course's
    current ones. They are required rather than defaulted so a new caller
    has to say which it means.
    """
    answered_keys = answered_keys or set()
    review = [
        q
        for q in questions_service.for_package(db, package.id)
        if q.kind == "review"
    ]
    questions_at: dict[str, list] = {}
    for q in review:
        questions_at.setdefault(q.after_section, []).append(q)

    sections: list[ReaderSection] = []
    # Body sections open in order; the first unanswered gate closes every
    # body section after it. Reference sections are never affected.
    locked_from_here = False
    for section in package.sections:
        placed = questions_at.get(section.section_key, [])
        is_reference = section.role in UNGATED_ROLES
        locked = gated and locked_from_here and not is_reference
        sections.append(
            ReaderSection(
                section_key=section.section_key,
                role=section.role,
                title=section.title,
                position=section.position,
                word_count=section.word_count,
                counted=section.counted,
                locked=locked,
                markdown=(
                    None if locked else strip_html_comments(section.markdown)
                ),
                question_keys=[q.question_key for q in placed],
            )
        )
        if section.role == ROLE_BODY and any(
            q.question_key not in answered_keys for q in placed
        ):
            locked_from_here = True

    unlocked = {s.section_key for s in sections if not s.locked}
    # 037: a gated section is complete when its review gate has been
    # passed — the same condition the loop above uses to close the
    # sections after it, read the other way round: open, and every
    # question placed after it answered. Derived here from the sections
    # just built, never stored, so it cannot drift from the gate it
    # describes. The preview has no participant and so no progress.
    gated_sections = [s for s in sections if s.role == ROLE_BODY]
    sections_completed = (
        sum(
            1
            for s in gated_sections
            if not s.locked
            and all(key in answered_keys for key in s.question_keys)
        )
        if gated
        else 0
    )
    return ReaderLesson(
        lesson_id=package.lesson_id,
        title=package.title,
        kind=package.kind,
        word_count=package.word_count,
        course_title=course_title,
        lesson_position=lesson_position,
        lesson_count=lesson_count,
        section_count=len(gated_sections),
        sections_completed=sections_completed,
        sections=sections,
        media=[
            ReaderMedia(
                media_key=item.media_key,
                after_section=item.after_section,
                url=storage.url_for(item.storage_key, VIDEO_URL_SECONDS),
                duration_seconds=item.duration_seconds,
            )
            for item in package.media
            if item.after_section in unlocked
            and package.media_purged_at is None
        ],
        media_removed=package_lifecycle.media_removed_message(package),
        # A question is served with the section it follows, so a question
        # behind a closed gate is not served either — its stem is part of
        # the material the gate is withholding.
        questions=[
            ReaderQuestion(
                question_key=q.question_key,
                after_section=q.after_section,
                stem=q.stem,
                choices=[
                    {"choice_key": c.choice_key, "text": c.text}
                    for c in q.choices
                ],
                answered=q.question_key in answered_keys,
            )
            for q in review
            if q.after_section in unlocked
        ],
    )
