"""Anthropic client for the call report, on `settings.model_default`.

The same `LlmClient` shape as `llm.AnthropicLlmClient`, which is tuned for fast
menu decisions (the fast model, a small token budget, no retries). A report is
written once, after the call, with the applicant off the line: it gets the default
model, room for a longer answer, and one SDK retry.
"""

import asyncio
import logging

import anthropic
import pydantic

from app.phone.llm import Effort, LlmError
from app.settings import get_settings

logger = logging.getLogger(__name__)

_MAX_TOKENS = 4096


class AnthropicReportClient:
    def __init__(self, *, effort: Effort = "medium") -> None:
        settings = get_settings()
        self._model = settings.model_default
        self._effort: Effort = effort
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None, max_retries=1
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
            "report llm: %d in, %d cached, %d out",
            response.usage.input_tokens,
            response.usage.cache_read_input_tokens or 0,
            response.usage.output_tokens,
        )
        return response.parsed_output

    async def close(self) -> None:
        await self._client.close()
