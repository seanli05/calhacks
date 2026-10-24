"""Facts from a user's message: one fast-model structured-output call (decision 13).

The model only proposes. The filter in `filters.py` decides what's stored, so a
model that slips (an asylum detail labeled `household`) is still caught in code.
"""

import logging
from collections.abc import Sequence
from typing import Literal

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.memory.prompts import EXTRACT_FACTS_SYSTEM

logger = logging.getLogger(__name__)

EXTRACT_TIMEOUT_S = 15.0

Category = Literal[
    "immigration",
    "asylum_claim",
    "identifier",
    "income",
    "health",
    "household",
    "contact",
    "other",
]


class ExtractedFact(BaseModel):
    fact: str
    category: Category


class ExtractedProfile(BaseModel):
    county: str | None = None
    household_size: int | None = None
    contact_preference: str | None = None


class Extraction(BaseModel):
    facts: list[ExtractedFact]
    profile: ExtractedProfile


class ExtractionError(Exception):
    """The model call failed or returned nothing usable; the job fails."""


class FactExtractor:
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        timeout_s: float = EXTRACT_TIMEOUT_S,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_s = timeout_s

    async def extract(
        self, text_en: str, previous_reply_en: str | None, known_facts: Sequence[str]
    ) -> Extraction:
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=2048,
                system=EXTRACT_FACTS_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": _user_content(
                            text_en, previous_reply_en, known_facts
                        ),
                    }
                ],
                output_config={"effort": "low"},
                output_format=Extraction,
                timeout=self._timeout_s,
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"extraction failed ({type(exc).__name__})") from exc
        if response.parsed_output is None:
            raise ExtractionError("extraction returned no output")
        return response.parsed_output

    async def close(self) -> None:
        await self._client.close()


def _user_content(
    text_en: str, previous_reply_en: str | None, known_facts: Sequence[str]
) -> str:
    known = "\n".join(f"- {fact}" for fact in known_facts) or "(none)"
    return "\n".join(
        [
            f"<known_facts>\n{known}\n</known_facts>",
            f"<previous_reply>\n{previous_reply_en or '(none)'}\n</previous_reply>",
            f"<message>\n{text_en}\n</message>",
        ]
    )
