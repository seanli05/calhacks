"""What the user hasn't answered yet, as the orchestrator turn sees it.

The pipe answers a bare number or yes/no word in code; anything else goes to the
turn, which gets this snapshot and answers through guarded tools (tools.py). Built
by the pipe from the same sources as `InboundPipe.question_open`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.db import tables


class QuestionKind(StrEnum):
    CALL_QUESTION = "call_question"
    CALL_CONSENT = "call_consent"
    SAME_OR_NEW = "same_or_new"
    SAVE_FACTS = "save_facts"


@dataclass(frozen=True)
class OpenQuestion:
    kind: QuestionKind
    # The question ID (call_question) or case ID (call_consent); None otherwise.
    ref: str | None
    options_en: tuple[str, ...]


# Settles "same letter or new?" with 1 (same) or 2 (new), sending no confirmation;
# returns the template that would confirm it, or None if the question isn't open.
SettleSameOrNew = Callable[[tables.User, int], Awaitable[str | None]]


@dataclass(frozen=True)
class OpenQuestions:
    questions: tuple[OpenQuestion, ...] = ()
    # The pipe's own answer path for "same letter or new?" (it holds the photos).
    settle_same_or_new: SettleSameOrNew | None = field(default=None, compare=False)

    def of(self, kind: QuestionKind) -> OpenQuestion | None:
        return next((q for q in self.questions if q.kind == kind), None)

    def render(self) -> list[str]:
        """The turn's `<open_questions>` block, in English."""
        lines = ["<open_questions>"]
        for question in self.questions:
            ref = f" {_REF_NAMES[question.kind]}={question.ref}" if question.ref else ""
            options = "; ".join(
                f'{i} "{option}"' for i, option in enumerate(question.options_en, 1)
            )
            lines.append(f"- {question.kind}{ref}: {options}")
        if not self.questions:
            lines.append("(none)")
        lines.append("</open_questions>")
        return lines


_REF_NAMES = {
    QuestionKind.CALL_QUESTION: "question_id",
    QuestionKind.CALL_CONSENT: "case_id",
}

CONSENT_OPTIONS_EN = ("Yes, call", "No, thanks")
SAME_OR_NEW_OPTIONS_EN = ("Another page of the same letter", "A new letter")
SAVE_FACTS_OPTIONS_EN = ("Yes, save it", "No, don't save it")
