"""Glossary grounding (Plan.md → Shared modules; Goal 5.3): the preset glossary's
translations for the terms a text uses, so the translator says "entrevista de asilo"
the way USCIS does instead of picking its own words.

Only the terms found in the text go into the prompt; the whole glossary would bury
the few that matter. Matching ignores case, accents and a plural ending, since users
write "interprete" and "solicitantes"; in Dari it also ignores the zero-width
non-joiner, Arabic letter forms (ي, ك) and the plural endings ها and ان
("متقاضیان", "نامه‌ها"). English terms also match their verb forms: "dismissed"
brings in "dismissal", whose Dari must not become the word for a denial. If the
glossary can't be read, translation goes ahead without it rather than wait.
"""

import asyncio
import logging
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.contracts.common import LanguageCode
from app.db import reads
from app.translation.prompts import GLOSSARY_SECTION

logger = logging.getLogger(__name__)

GLOSSARY_TIMEOUT_S = 2.0
GLOSSARY_TTL_S = 600.0
RETRY_AFTER_FAILURE_S = 30.0
MAX_TERMS = 30


class GlossaryRow(Protocol):
    term: str
    translation: str


Loader = Callable[[LanguageCode], Awaitable[Sequence[GlossaryRow]]]


@dataclass(frozen=True)
class Term:
    english: str
    translation: str
    english_pattern: re.Pattern[str]
    translation_pattern: re.Pattern[str]

    @classmethod
    def from_row(cls, row: GlossaryRow) -> "Term":
        return cls(
            english=row.term,
            translation=row.translation,
            english_pattern=_phrase_pattern(row.term, english=True),
            translation_pattern=_phrase_pattern(row.translation),
        )


class Glossary:
    """Glossary terms per language, read through `reads.get_glossary` and cached.

    A failed read keeps whatever was cached (or nothing) and is retried after
    `RETRY_AFTER_FAILURE_S`, so a database outage doesn't add the timeout to every
    translation.
    """

    def __init__(
        self,
        load: Loader = reads.get_glossary,
        timeout_s: float = GLOSSARY_TIMEOUT_S,
        ttl_s: float = GLOSSARY_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._timeout_s = timeout_s
        self._ttl_s = ttl_s
        self._clock = clock
        self._cache: dict[LanguageCode, tuple[float, list[Term]]] = {}

    async def section(
        self, text: str, language: LanguageCode, *, source_is_english: bool
    ) -> str:
        """A prompt section listing the glossary terms `text` uses, as source →
        target, or "" when it uses none."""
        found = find_terms(
            text, await self._terms(language), source_is_english=source_is_english
        )
        if not found:
            return ""
        lines = "\n".join(
            f"- {t.english} → {t.translation}"
            if source_is_english
            else f"- {t.translation} → {t.english}"
            for t in found
        )
        return GLOSSARY_SECTION.format(lines=lines)

    async def _terms(self, language: LanguageCode) -> list[Term]:
        now = self._clock()
        cached = self._cache.get(language)
        if cached is not None and now < cached[0]:
            return cached[1]
        try:
            async with asyncio.timeout(self._timeout_s):
                rows = await self._load(language)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            logger.warning(
                "Glossary read failed language=%s: %s", language, type(exc).__name__
            )
            terms = cached[1] if cached is not None else []
            self._cache[language] = (now + RETRY_AFTER_FAILURE_S, terms)
            return terms
        terms = [Term.from_row(row) for row in rows]
        self._cache[language] = (now + self._ttl_s, terms)
        return terms


def find_terms(
    text: str, terms: Sequence[Term], *, source_is_english: bool
) -> list[Term]:
    """The terms whose source side appears in `text`, longest first, at most
    `MAX_TERMS`."""
    normalized = _normalize(text)
    found = [
        term
        for term in terms
        if (
            term.english_pattern if source_is_english else term.translation_pattern
        ).search(normalized)
    ]
    found.sort(key=lambda t: (-len(t.english), t.english))
    return found[:MAX_TERMS]


_PERSIAN_LETTERS = str.maketrans(
    {"ي": "ی", "ى": "ی", "ك": "ک", "ـ": None, "\u200c": " "}
)


def _normalize(text: str) -> str:
    """Lowercase with accents stripped: "Intérprete" and "interprete" match. Persian
    script: one letter form, and a zero-width non-joiner read as a space."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.translate(_PERSIAN_LETTERS)


def _phrase_pattern(phrase: str, *, english: bool = False) -> re.Pattern[str]:
    """Whole words, any spacing, an optional plural "s"/"es" (or Dari "ها"/"ان"). A
    `<ref:receipt_number>` placeholder doesn't match "receipt number": the underscore
    isn't a space."""
    *head, last = _normalize(phrase).split()
    body = r"\s+".join([*(re.escape(word) for word in head), _last_word(last, english)])
    return re.compile(rf"(?<!\w){body}(?!\w)")


def _last_word(word: str, english: bool) -> str:
    """The phrase's last word with its endings. English: also the verb forms of a
    noun in -al or a verb in -e ("dismissal": "dismissed"; "denial": "denied";
    "reschedule": "rescheduling")."""
    if not english:
        return rf"{re.escape(word)}(?:e?s|\s?ها|ان)?"
    stem = word[:-2] if word.endswith("al") else word.removesuffix("e")
    return rf"(?:{re.escape(word)}(?:e?s)?|{re.escape(stem)}(?:ed|ing|es))"
