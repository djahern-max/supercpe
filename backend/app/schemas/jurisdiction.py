from datetime import date
from typing import Literal

from pydantic import BaseModel

CREDIT_INCREMENT = Literal["one_fifth", "one_half", "whole", "unknown"]


class AdminJurisdictionOut(BaseModel):
    jurisdiction: str
    name: str
    credit_increment: CREDIT_INCREMENT
    non_technical_cap_note: str
    source: str
    verified_on: date | None
    notes: str
    # Both derived live, never stored.
    displayable: bool
    verification_stale: bool


class JurisdictionUpdate(BaseModel):
    credit_increment: CREDIT_INCREMENT
    non_technical_cap_note: str = ""
    source: str = ""
    verified_on: date | None = None
    notes: str = ""


class JurisdictionNoteOut(BaseModel):
    """The per-viewer hint. Deliberately not part of the 016 public
    course payload: that payload is public and cacheable, this depends on
    who is asking."""

    jurisdiction: str
    jurisdiction_name: str
    credit_increment: Literal["one_fifth", "one_half", "whole"]
    # The 005 stored award, displayed unchanged.
    recommended_credit: str
    # Present only when the board's increment is coarser than one-fifth:
    # the award rounded down to it, computed per request (7.01.1).
    board_rounded_credit: str | None
    # Present only when the course's field of study is non-technical.
    non_technical_cap_note: str | None
    verified_on: date
    # FINAL_AUTHORITY_SENTENCE, verbatim (7.01).
    final_authority: str
