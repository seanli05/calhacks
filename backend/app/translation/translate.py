"""Two-way translation at the edges (Plan.md → Shared modules; rule 6): user text
into English on the way in, the orchestrator's English replies into the user's
language on the way out.

A second language is a `REGISTERS` entry, not code. Glossary grounding (5.3) and the
dates-survive check (5.4) come later.
"""

import logging
from functools import lru_cache

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.contracts.common import LanguageCode
from app.settings import get_settings
from app.translation.prompts import (
    FROM_ENGLISH_SYSTEM,
    LABELS_FROM_ENGLISH_SYSTEM,
    TO_ENGLISH_SYSTEM,
)

logger = logging.getLogger(__name__)

TRANSLATE_TIMEOUT_S = 8.0

LANGUAGE_NAMES: dict[LanguageCode, str] = {"es": "Spanish", "en": "English"}

REGISTERS: dict[LanguageCode, str] = {
    "es": (
        "Write warm, simple Spanish that someone with little schooling can follow. "
        "Use formal usted, never tú. Short sentences."
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
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_s = timeout_s

    async def to_english(self, text: str, language: LanguageCode) -> str | None:
        """`text` in English, or None if the call fails. English is returned as is."""
        if language == "en":
            return text
        system = TO_ENGLISH_SYSTEM.format(language=_name(language))
        return await self._translate(text, system, language)

    async def from_english(self, text_en: str, language: LanguageCode) -> str | None:
        """`text_en` in `language`, or None if the call fails."""
        if language == "en":
            return text_en
        system = FROM_ENGLISH_SYSTEM.format(
            language=_name(language),
            register=REGISTERS.get(language, _DEFAULT_REGISTER),
        )
        return await self._translate(text_en, system, language)

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
        return translated.labels

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


def _name(language: LanguageCode) -> str:
    return LANGUAGE_NAMES.get(language, f"the language with ISO 639-1 code {language}")


@lru_cache
def get_translator() -> Translator | None:
    """The shared translator, or None without an Anthropic key."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return Translator(
        AsyncAnthropic(api_key=settings.anthropic_api_key), settings.model_fast
    )
