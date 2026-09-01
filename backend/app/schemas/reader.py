"""Reader, search, and glossary payloads (023).

Same rule as `schemas/player`: nothing here carries the answer key. A
reader question has choice keys and text, never `is_correct` and never
feedback — feedback comes only from the grading endpoint, only after an
answer. Tests walk these payloads asserting the fields are absent.

A locked section carries `markdown: null`. That is the gate: the text of
a section a participant has not yet earned is not in the response at all.
"""

from pydantic import BaseModel, ConfigDict

from app.schemas.player import PlayChoice


class ReaderQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_key: str
    after_section: str
    stem: str
    choices: list[PlayChoice]
    answered: bool


class ReaderMediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_key: str
    after_section: str
    url: str
    duration_seconds: int


class ReaderSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_key: str
    role: str
    title: str
    position: int
    word_count: int
    # Whether this section's words entered the credit formula (7.02.5).
    counted: bool
    locked: bool
    markdown: str | None
    # Every review question placed after this section; all of them gate
    # the next body section.
    question_keys: list[str]


class ReaderLessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lesson_id: str
    title: str
    kind: str
    word_count: int
    sections: list[ReaderSectionOut]
    media: list[ReaderMediaOut]
    questions: list[ReaderQuestionOut]


class SearchHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    package_id: int
    lesson_id: str
    section_key: str
    section_title: str
    role: str
    snippets: list[str]
    match_count: int


class SearchResultsOut(BaseModel):
    query: str
    hits: list[SearchHitOut]


class GlossaryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term: str
    definition: str
    package_id: int
    lesson_id: str
    section_key: str | None


class GlossaryOut(BaseModel):
    terms: list[GlossaryEntryOut]
