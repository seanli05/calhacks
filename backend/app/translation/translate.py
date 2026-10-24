"""Two-way translation at the edges (Plan.md → Shared modules; rule 6): user text
into English on the way in, the orchestrator's English replies into the user's
language on the way out.

A second language is a `REGISTERS` entry, not code. Each prompt carries the glossary
terms the text uses (`translation/glossary.py`, 5.3). Every number in the source must
come back with the same value and no number may be added (5.4), and every list item
must come back; otherwise the translation is retried once, then not used, and the
caller falls back to its template. Right-to-left output gets direction isolates
around its Latin fragments (`translation/script.py`).
"""

import logging
import re
from functools import lru_cache

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.contracts.common import LanguageCode
from app.settings import get_settings
from app.translation.glossary import Glossary
from app.translation.prompts import (
    CONTEXT_SECTION,
    FROM_ENGLISH_SYSTEM,
    LABELS_FROM_ENGLISH_SYSTEM,
    RETRY_REMINDER,
    TO_ENGLISH_SYSTEM,
)
from app.translation.script import for_display, numbers_kept

logger = logging.getLogger(__name__)

TRANSLATE_TIMEOUT_S = 8.0
_LIST_ITEM = re.compile(r"^\s*[-•*]\s", re.MULTILINE)

LANGUAGE_NAMES: dict[LanguageCode, str] = {
    "es": "Spanish",
    "en": "English",
    "fa": "Dari (Afghan Persian)",
}

# The Dari word choices follow USCIS's Dari pages and the glossary; the month names
# and times follow USCIS's Dari page, UNAMA's Dari reports and Da Afghanistan Bank.
REGISTERS: dict[LanguageCode, str] = {
    "es": (
        "Write warm, simple Spanish that someone with little schooling can follow. "
        "Use formal usted, never tú. Short sentences."
    ),
    "fa": (
        "Write Afghan Dari, as it is written in Afghanistan, not Iranian Farsi: "
        "warm and simple, for someone with little schooling, with the polite شما "
        "and short sentences. Use Afghan words: بلی (not بله), تشکر (not ممنون or "
        "مرسی), حالا (not الان), معلومات (not اطلاعات), تیلفون (not تلفن), دوسیه "
        "(not پرونده), مشوره (not مشاوره), محکمه (not دادگاه), ضرورت (not نیاز). "
        "Call the agency «ادارهٔ USCIS». Write Gregorian dates day first, with the "
        "Afghan month names: جنوری، فبروری، مارچ، اپریل، می، جون، جولای، اگست، "
        "سپتمبر، اکتوبر، نومبر، دسمبر (for example ۱۸ نومبر ۲۰۲۶). Write times "
        "with صبح, بعد از ظهر or شب (for example ۸:۳۰ صبح). Write numbers, dates "
        "and times in Persian digits (۰۱۲۳۴۵۶۷۸۹); keep form names, phone numbers "
        "and URLs in Latin characters exactly as written. Write ID or identity "
        "document as سند هویت: تذکره is only the Afghan national ID."
    ),
}
_DEFAULT_REGISTER = "Write warm, simple, polite language. Short sentences."


class _Translated(BaseModel):
    text: str


class _Labels(BaseModel):
    labels: list[str]


class Translator:
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        timeout_s: float = TRANSLATE_TIMEOUT_S,
        glossary: Glossary | None = None,
    ) -> None:
        """Without `glossary`, prompts carry no glossary terms."""
        self._client = client
        self._model = model
        self._timeout_s = timeout_s
        self._glossary = glossary

    async def to_english(self, text: str, language: LanguageCode) -> str | None:
        """`text` in English, or None if the call fails or a number didn't survive.
        English is returned as is."""
        if language == "en":
            return text
        system = TO_ENGLISH_SYSTEM.format(language=_name(language))
        system += await self._glossary_section(text, language, source_is_english=False)
        return await self._translate_checked(text, system, language)

    async def from_english(
        self, text_en: str, language: LanguageCode, *, context: str | None = None
    ) -> str | None:
        """`text_en` in `language`, ready to show, or None if the call fails or a
        number didn't survive. `context` says what the text is when a fragment could
        be misread (a call's purpose read as a request to the user)."""
        if language == "en":
            return text_en
        system = FROM_ENGLISH_SYSTEM.format(
            language=_name(language),
            register=REGISTERS.get(language, _DEFAULT_REGISTER),
        )
        if context:
            system += CONTEXT_SECTION.format(context=context)
        system += await self._glossary_section(
            text_en, language, source_is_english=True
        )
        translated = await self._translate_checked(text_en, system, language)
        return for_display(translated, language) if translated is not None else None

    async def labels_from_english(
        self, labels_en: list[str], language: LanguageCode
    ) -> list[str] | None:
        """Short labels (phone menu options) in `language`, in the same order, or
        None if the call fails or the count doesn't match."""
        if language == "en":
            return labels_en
        system = LABELS_FROM_ENGLISH_SYSTEM.format(
            language=_name(language),
            register=REGISTERS.get(language, _DEFAULT_REGISTER),
        )
        system += await self._glossary_section(
            "\n".join(labels_en), language, source_is_english=True
        )
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": _Labels(labels=labels_en).model_dump_json(),
                    }
                ],
                output_config={"effort": "low"},
                output_format=_Labels,
                timeout=self._timeout_s,
            )
        except anthropic.APIError as exc:
            logger.warning(
                "Label translation failed language=%s: %s",
                language,
                type(exc).__name__,
            )
            return None
        translated = response.parsed_output
        if (
            translated is None
            or len(translated.labels) != len(labels_en)
            or not all(label.strip() for label in translated.labels)
        ):
            logger.warning("Label translation came back unusable language=%s", language)
            return None
        if not all(
            _usable(en, label, language)
            for en, label in zip(labels_en, translated.labels, strict=True)
        ):
            return None
        return [for_display(label, language) for label in translated.labels]

    async def _glossary_section(
        self, text: str, language: LanguageCode, *, source_is_english: bool
    ) -> str:
        if self._glossary is None:
            return ""
        return await self._glossary.section(
            text, language, source_is_english=source_is_english
        )

    async def _translate_checked(
        self, text: str, system: str, language: LanguageCode
    ) -> str | None:
        """A translation that isn't faithful (a number changed, dropped or added; a
        list item left out) is retried once with a reminder, then given up on."""
        translated = await self._translate(text, system, language)
        if translated is None or _faithful(text, translated):
            return translated
        logger.warning("Translation not faithful language=%s; retrying", language)
        translated = await self._translate(text, system + RETRY_REMINDER, language)
        return translated if _usable(text, translated, language) else None

    async def _translate(
        self, text: str, system: str, language: LanguageCode
    ) -> str | None:
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": text}],
                output_config={"effort": "low"},
                output_format=_Translated,
                timeout=self._timeout_s,
            )
        except anthropic.APIError as exc:
            logger.warning(
                "Translation failed language=%s: %s", language, type(exc).__name__
            )
            return None
        translated = response.parsed_output
        if translated is None or not translated.text.strip():
            logger.warning("Translation came back empty language=%s", language)
            return None
        return translated.text


def _usable(source: str, translated: str | None, language: LanguageCode) -> bool:
    """An unfaithful translation is never shown; the caller's template carries the
    facts instead."""
    if translated is None:
        return False
    if _faithful(source, translated):
        return True
    # No text in the log: the numbers may be the user's.
    logger.warning("Translation not faithful language=%s; not used", language)
    return False


def _faithful(source: str, translated: str) -> bool:
    """The same numbers (5.4) and as many list items: a dropped "- bring your
    passport" loses a fact as surely as a changed date."""
    return numbers_kept(source, translated) and len(_LIST_ITEM.findall(source)) == len(
        _LIST_ITEM.findall(translated)
    )


def _name(language: LanguageCode) -> str:
    return LANGUAGE_NAMES.get(language, f"the language with ISO 639-1 code {language}")


@lru_cache
def get_translator() -> Translator | None:
    """The shared translator, or None without an Anthropic key."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return Translator(
        AsyncAnthropic(api_key=settings.anthropic_api_key),
        settings.model_fast,
        glossary=Glossary(),
    )


async def localize(
    translator: Translator | None,
    text_en: str,
    language: LanguageCode,
    *,
    context: str | None = None,
) -> str | None:
    """`text_en` in `language`, or None when it can't be translated (no translator,
    or the call failed). Callers fall back to a template, never to English."""
    if language == "en":
        return text_en
    if translator is None:
        return None
    return await translator.from_english(text_en, language, context=context)
