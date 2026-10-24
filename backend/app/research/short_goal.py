"""R2's short call goal (C41): the brief's goal rewritten as one clause the user
reads in the consent question on a phone. The brief keeps the full goal, which the
phone agent and the dashboard read.

The input is the brief's goal, which never holds sensitive values; the job's leak
guard still checks R2 before it's written.
"""

import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

MAX_WORDS = 12
MAX_TOKENS = 64

SHORT_GOAL_SYSTEM = """\
You rewrite the goal of a phone call to a government office or other organization. \
The person whose letter it is reads your line on a phone before agreeing to the call.

Write one clause of at most 12 words. Start with a verb, address the person ("your \
interview"), keep only the main purpose, and end without a period. Output only the \
clause: no quotes, no explanation.

Example: "Ask the local asylum office or USCIS Contact Center about the interview, \
rescheduling, or attorney remote participation." becomes "Confirm your interview is \
still scheduled"."""


async def shorten_goal(
    goal_en: str, *, client: AsyncAnthropic, model: str
) -> str | None:
    """The short goal, or None when the model's answer doesn't fit (the orchestrator
    then falls back to the brief's goal)."""
    response = await client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        # A rewrite needs no reasoning, and thinking would use up MAX_TOKENS.
        thinking={"type": "disabled"},
        system=SHORT_GOAL_SYSTEM,
        messages=[{"role": "user", "content": goal_en}],
    )
    if response.stop_reason != "end_turn":
        logger.warning("short goal not used: stop_reason=%s", response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    return clean_goal(text)


def clean_goal(text: str) -> str | None:
    """One line, no quotes or trailing period, at most 12 words; None otherwise.
    Too long means the model ignored the rule, and a cut would leave a fragment."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    line = line.strip().strip("\"'“”").rstrip(" .;,:").strip()
    if not line or len(line.split()) > MAX_WORDS:
        return None
    return line
