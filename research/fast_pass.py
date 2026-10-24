"""Fast pass: letter pages -> R1, legitimacy signals, and sensitive values."""

from anthropic import AsyncAnthropic

from research.models import FastPassOutput
from research.preprocess import ContentBlock


async def run_fast_pass(
    blocks: list[ContentBlock],
    *,
    case_id: str,
    client: AsyncAnthropic,
    model: str,
    profile_county: str | None = None,
) -> FastPassOutput:
    """Extract the letter with structured outputs (no citations; quotes live in the schema).

    `profile_county` is a fallback when the letter names no county and a
    cross-check against scams. Sensitive values come back only in
    `sensitive_values`; R1 carries their refs. Caller enforces the 45 s timeout.
    """
    raise NotImplementedError
