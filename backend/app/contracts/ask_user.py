"""Phone agent asking the user mid-call, through the relay (Plan.md → P1)."""

from typing import Self

from pydantic import Field, model_validator

from app.contracts.common import CallId, Contract, QuestionId


class AskUserRequest(Contract):
    """P1. Options are 1-based (C5); on timeout the agent takes `default_option`,
    which is always the safest choice."""

    question_id: QuestionId
    call_id: CallId
    template: str
    options_en: list[str] = Field(min_length=1)
    default_option: int
    timeout_s: int = Field(gt=0)

    @model_validator(mode="after")
    def _default_option_in_range(self) -> Self:
        if not 1 <= self.default_option <= len(self.options_en):
            raise ValueError(
                f"default_option must be between 1 and {len(self.options_en)}"
            )
        return self


class AskUserReply(Contract):
    question_id: QuestionId
    choice: int = Field(ge=1)
    """1-based, matching what the user types (C5)."""
