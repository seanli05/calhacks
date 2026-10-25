"""Rule-based tips for the live call view: what the user could say next. No model
writes them, so the dashboard still never talks to the user free-form (rule 1):

- `ask`: the next of the brief's `questions_to_ask` the user hasn't asked yet, one
  at a time, as English to read out loud. The brief's questions are already shown
  on the case view before the call.
- `yourself`: when the officer asks something about the applicant's identity, a
  reminder that only the user answers it. It never carries an answer (rule 3).

A tip counts as used when the user's next line says it (for `ask`, most of the
question's words; for `yourself`, any reply).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

IDENTITY_QUESTION = re.compile(
    r"\b("
    r"(full|your|first|last|legal) name|spell (your|the)|"
    r"date of birth|birth ?date|born|d\.?o\.?b\.?|"
    r"a[- ]?number|alien (registration )?number|receipt number|case number|"
    r"social security|ssn|"
    r"(your|home|mailing|current) address|zip code|"
    r"verify (your )?identity|confirm (your|some) (identity|information|details)"
    r")\b",
    re.IGNORECASE,
)

MATCH_SHARE = 0.5
"""Share of a question's content words the user's line must contain to count as
asking it."""

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "you",
        "your",
        "can",
        "could",
        "would",
        "what",
        "when",
        "where",
        "which",
        "this",
        "that",
        "with",
        "have",
        "does",
        "from",
        "they",
        "them",
        "there",
        "their",
        "about",
        "need",
        "should",
        "will",
        "just",
        "also",
        "too",
        "into",
        "been",
        "were",
        "are",
        "was",
        "may",
        "might",
    ]
)

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "yourself": "This question is for you: answer it yourself. We never answer for you.",
    },
    "es": {
        "yourself": "Esta pregunta es para ti: contéstala tú. Nosotros nunca respondemos por ti.",
    },
}


def text(key: str, lang: str) -> str:
    return TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]


def _content_words(text_en: str) -> set[str]:
    return {w for w in _WORD.findall(text_en.lower()) if len(w) > 2 and w not in _STOP}


def says(line_en: str, question_en: str) -> bool:
    """True when `line_en` contains most of `question_en`'s content words."""
    wanted = _content_words(question_en)
    if not wanted:
        return False
    return len(wanted & _content_words(line_en)) / len(wanted) >= MATCH_SHARE


@dataclass(frozen=True)
class Tip:
    id: str
    kind: Literal["ask", "yourself"]
    line_id: str
    say_en: str | None


@dataclass
class Tips:
    """The tip state of one call, fed its lines in order."""

    call_id: str
    questions: list[str]
    _asked: set[int] = field(default_factory=set)
    _open_ask: tuple[str, int] | None = None
    _open_yourself: str | None = None
    _count: int = 0

    def after_agency(self, line_en: str, line_id: str) -> list[Tip]:
        tips: list[Tip] = []
        if IDENTITY_QUESTION.search(line_en) and self._open_yourself is None:
            tip = self._new("yourself", line_id, None)
            self._open_yourself = tip.id
            tips.append(tip)
        if self._open_ask is None:
            nxt = next(
                (i for i in range(len(self.questions)) if i not in self._asked), None
            )
            if nxt is not None:
                tip = self._new("ask", line_id, self.questions[nxt])
                self._open_ask = (tip.id, nxt)
                tips.append(tip)
        return tips

    def after_user(self, line_en: str) -> list[str]:
        """Ids of the tips this line used."""
        used: list[str] = []
        if self._open_yourself is not None:
            used.append(self._open_yourself)
            self._open_yourself = None
        for i, question in enumerate(self.questions):
            if i in self._asked or not says(line_en, question):
                continue
            self._asked.add(i)
            if self._open_ask is not None and self._open_ask[1] == i:
                used.append(self._open_ask[0])
                self._open_ask = None
        return used

    def _new(
        self, kind: Literal["ask", "yourself"], line_id: str, say_en: str | None
    ) -> Tip:
        tip = Tip(
            id=f"{self.call_id}_tip{self._count}",
            kind=kind,
            line_id=line_id,
            say_en=say_en,
        )
        self._count += 1
        return tip
