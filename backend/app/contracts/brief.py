"""Case brief stored in `case_briefs` and read by the phone agent (Plan.md → R2)."""

import datetime as dt
from typing import Self

from pydantic import Field, model_validator

from app.contracts.common import BriefId, CaseId, Contract
from app.contracts.results import Appointment, KeyFact

REQUIRED_MUST_NOT_DO: tuple[str, ...] = (
    "Never give the A-Number, receipt number, or date of birth",
    "Never discuss the asylum claim",
)
"""Always in a brief's `must_not_do` (C34, C35)."""


class RepQuestion(Contract):
    """A question the representative is likely to ask, and where the answer comes
    from. The agent never answers identity questions itself (rule 3)."""

    question: str
    answer_source: str


class CaseBrief(Contract):
    brief_id: BriefId
    case_id: CaseId
    doc_type: str
    issuer: str
    deadline: dt.date | None = None
    appointment: Appointment | None = None
    call_goal_en: str
    expected_menu_path: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    """English; the dashboard shows them before the call."""
    must_not_do: list[str] = Field(default_factory=lambda: list(REQUIRED_MUST_NOT_DO))
    glossary_terms: list[str] = Field(default_factory=list)
    facts: list[KeyFact] = Field(default_factory=list)
    handoff_note: str
    likely_rep_questions: list[RepQuestion] = Field(default_factory=list)
    contingencies: list[str] = Field(default_factory=list)
    open_uncertainties: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _required_must_not_do(self) -> Self:
        missing = [
            rule for rule in REQUIRED_MUST_NOT_DO if rule not in self.must_not_do
        ]
        if missing:
            raise ValueError(f"must_not_do is missing required rules: {missing}")
        return self
