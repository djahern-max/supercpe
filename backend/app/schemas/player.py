from pydantic import BaseModel

# The player payloads never carry the answer key: no is_correct, no correct
# choice key, no feedback before an answer is submitted. Grading happens
# server-side and tests walk these payloads asserting the fields are absent.


class PlayBlock(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float


class PlayChoice(BaseModel):
    choice_key: str
    text: str


class PlayQuestion(BaseModel):
    question_key: str
    after_block: int
    stem: str
    choices: list[PlayChoice]
    # 031: whether this participant has already answered it, derived from
    # `review_answers` exactly as the reader payload's `answered` is; the
    # preview has no record and always says False. The player's seek
    # ceiling is the earliest review point whose question is unanswered.
    # A fact about the participant's own record, never the answer key.
    answered: bool


class PlayLesson(BaseModel):
    """Everything the player needs for one lesson."""

    lesson_id: str
    title: str
    video_url: str
    duration_seconds: int
    blocks: list[PlayBlock]
    questions: list[PlayQuestion]


class ReviewAnswer(BaseModel):
    choice_key: str


class ReviewResult(BaseModel):
    """5.01.2.2: feedback always, and at least correct or incorrect. The
    correct choice key is included so the player can mark the right row
    after the verdict; it is only ever served after an answer."""

    correct: bool
    feedback: str
    correct_choice_key: str
