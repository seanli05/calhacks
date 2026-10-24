"""Deep pass: legitimacy check and official-number lookup on the web."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from anthropic import AsyncAnthropic

from research.models import DeepFindings, LegitimacySignals

LogFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]
"""(event_type, summary_en, data) for research.search / research.fetch / research.check."""


async def run_deep_pass(
    signals: LegitimacySignals,
    call_purpose: str | None,
    county: str | None,
    *,
    client: AsyncAnthropic,
    model: str,
    http: httpx.AsyncClient,
    log: LogFn | None = None,
) -> DeepFindings:
    """Verify the letter's issuer and find its official number.

    Manual loop with server `web_search` plus client `fetch_page`; resends on
    `pause_turn`. Sees only legitimacy signals, never personal data.
    `official_phone` is set only when `checks.phone_on_page` finds it on a page
    from a trusted domain. Caller enforces the 180 s timeout.
    """
    raise NotImplementedError
