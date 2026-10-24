"""Detect which language a user wrote in, for the first-contact language pick."""

import logging
import re

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.contracts.common import LanguageCode
from app.translation.prompts import DETECT_LANGUAGE_SYSTEM

logger = logging.getLogger(__name__)

DETECT_TIMEOUT_S = 5.0
_ISO_639_1 = re.compile(r"^[a-z]{2}$")
# Three-letter codes the model may give for Persian: Dari ("prs") and Persian
# ("fas", "per") are all "fa" here, the code the templates use for Dari.
_ALIASES: dict[str, LanguageCode] = {"prs": "fa", "fas": "fa", "per": "fa"}


class _Detected(BaseModel):
    language: str | None


async def detect_language(
    client: AsyncAnthropic, model: str, text: str
) -> LanguageCode | None:
    """The ISO 639-1 code of `text`, or None when unsure or when the call fails.
    None is always safe: the caller falls back to the language menu."""
    try:
        response = await client.messages.parse(
            model=model,
            max_tokens=1024,
            system=DETECT_LANGUAGE_SYSTEM,
            messages=[{"role": "user", "content": text}],
            output_config={"effort": "low"},
            output_format=_Detected,
            timeout=DETECT_TIMEOUT_S,
        )
    except anthropic.APIError as exc:
        logger.warning("Language detection failed: %s", type(exc).__name__)
        return None
    detected = response.parsed_output
    if detected is None or detected.language is None:
        return None
    code = detected.language.strip().lower()
    code = _ALIASES.get(code, code)
    return code if _ISO_639_1.match(code) else None
