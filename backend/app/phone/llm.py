"""Thin Anthropic wrapper for the phone agent's fast decisions (menu, line phase).

One structured call per decision: a static system prompt (cached), one user message,
a Pydantic output type. Callers code against `LlmClient` so tests use fakes. Every
failure comes out as `LlmError`, so callers don't import the SDK to handle errors.
"""

import asyncio
import logging
from typing import Literal, Protocol

import anthropic
import pydantic

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Thinking counts toward max_tokens; this leaves room for a little plus the answer.
_MAX_TOKENS = 1024

type Effort = Literal["low", "medium", "high"]


class LlmError(Exception):
    """The call failed: timeout, API error, refusal, or output that didn't validate."""


class LlmClient(Protocol):
    async def parse[T: pydantic.BaseModel](
        self, *, system: str, user: str, output_type: type[T], timeout_s: float
    ) -> T: ...


class AnthropicLlmClient:
    """`LlmClient` on the Anthropic SDK with `settings.model_fast`.

    SDK retries are off: a retry lands after the menu has moved on, and the next
    utterance is a fresher retry anyway. `last_usage` is kept for the eval's cache
    check.
    """

    def __init__(self, *, effort: Effort = "low") -> None:
        settings = get_settings()
        self._model = settings.model_fast
        self._effort: Effort = effort
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None, max_retries=0
        )
        self.last_usage: anthropic.types.Usage | None = None

    async def parse[T: pydantic.BaseModel](
        self, *, system: str, user: str, output_type: type[T], timeout_s: float
    ) -> T:
        try:
            async with asyncio.timeout(timeout_s):
                response = await self._client.messages.parse(
                    model=self._model,
                    max_tokens=_MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user}],
                    output_format=output_type,
                    output_config={"effort": self._effort},
                    timeout=timeout_s,
                )
        except TimeoutError as exc:
            raise LlmError(f"timed out after {timeout_s}s") from exc
        except anthropic.APIError as exc:
            raise LlmError(f"API error: {type(exc).__name__}") from exc
        except pydantic.ValidationError as exc:
            raise LlmError("output didn't match the schema") from exc

        self.last_usage = response.usage
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise LlmError(f"no parsed output (stop_reason={response.stop_reason})")
        logger.debug(
            "llm %s: %d in, %d cached, %d out",
            output_type.__name__,
            response.usage.input_tokens,
            response.usage.cache_read_input_tokens or 0,
            response.usage.output_tokens,
        )
        return response.parsed_output
