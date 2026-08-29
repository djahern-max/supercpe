from datetime import datetime

from pydantic import BaseModel


class EvaluationPrompt(BaseModel):
    key: str
    text: str


class MyEvaluationInfo(BaseModel):
    """Whether the prompt should appear for one completion, and the exact
    wording to ask with (from `app/constants/evaluation.py`)."""

    due: bool
    submitted: bool
    scale_min: int
    scale_max: int
    prompts: list[EvaluationPrompt]


class EvaluationSubmit(BaseModel):
    """The four rated elements; item 5 (instructors) is never accepted.
    The service validates keys and scale."""

    ratings: dict[str, int]
    comments: str = ""


class EvaluationRowOut(BaseModel):
    id: int
    submitted_at: datetime
    objectives_met: int
    prerequisites_appropriate: int
    materials_relevant: int
    time_appropriate: int
    # Always null: not applicable to self study, surfaced so the admin
    # view visibly answers 4.04.1 item 5.
    instructors_effective: int | None
    comments: str


class AdminEvaluationsOut(BaseModel):
    """The admin summary page: 4.04.2 wants the developer informed of
    results; until email exists (018), this page names them."""

    course_code: str
    developer_name: str | None
    summary: dict
    rows: list[EvaluationRowOut]


class EvaluationReviewCreate(BaseModel):
    note: str = ""
    informed_developer: bool = False


class EvaluationReviewOut(BaseModel):
    id: int
    reviewed_at: datetime
    reviewed_by_email: str
    note: str
    informed_developer: bool
    summary_snapshot: dict
