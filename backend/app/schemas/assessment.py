from datetime import datetime

from pydantic import BaseModel

# Attempt results are deliberately NOT modeled here: a response_model with
# optional per-question fields could serialize `is_correct: null` into a
# failed attempt's payload. `assessment.result` builds plain dicts and the
# result endpoints return them as-is, so a failed attempt's payload simply
# has no per-question keys at all (6.01.2 sub-ii).


class AssessmentChoice(BaseModel):
    choice_id: int
    text: str


class AssessmentQuestion(BaseModel):
    """A question as served to a participant taking the assessment: no
    answer key, no feedback, no verdicts (6.01.2 sub-ii)."""

    question_id: int
    stem: str
    choices: list[AssessmentChoice]


class AssessmentInfo(BaseModel):
    course_code: str
    title: str
    question_count: int
    passing_pct: str
    retakes_allowed: bool
    open_attempt_id: int | None
    questions: list[AssessmentQuestion]


class AttemptStarted(BaseModel):
    attempt_id: int
    status: str
    question_count: int
    passing_pct: str
    started_at: datetime


class AnswersRequest(BaseModel):
    """{question_id: choice_id}, partial for saves, complete for submit."""

    answers: dict[int, int]


class AnswersSaved(BaseModel):
    attempt_id: int
    answered: int
    question_count: int


class AdminAttemptAnswer(BaseModel):
    """One answer as the admin sees it — including correctness for failed
    attempts. The admin may see everything; the participant may not."""

    question_id: int
    question_key: str
    stem: str
    chosen_choice_id: int
    chosen_text: str
    correct_choice_id: int
    is_correct: bool | None
    answered_at: datetime


class AdminAttempt(BaseModel):
    id: int
    is_preview: bool
    preview_id: str | None
    enrollment_id: int | None
    status: str
    score_pct: str | None
    passing_pct: str
    question_count: int
    correct_count: int | None
    started_at: datetime
    submitted_at: datetime | None
    package_versions: list
    answers: list[AdminAttemptAnswer]
