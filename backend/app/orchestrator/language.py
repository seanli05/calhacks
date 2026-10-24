"""First-contact language pick (team decision, Oct 23).

A first message with text gets a one-tap confirm in the detected language; a
photo-only one gets the multilingual menu. No silent detection: short replies are
ambiguous, and a relative may type in English for the parent who takes the call.

The pending prompt is read back from the message log (the user's last outbound
language template), so it survives a restart.
"""

import re
from dataclasses import dataclass

from app.contracts import MessageDirection
from app.contracts.common import LanguageCode, UserId
from app.db import reads, tables
from app.relay.templates import LANGUAGES

CONFIRM = "language.confirm"
MENU = "language.menu"
_PROMPTS = {CONFIRM, MENU}
_YES = {"si", "sí", "yes"}
_CHOICE = re.compile(r"^(\d{1,2})[.)]?$")


def parse_choice(text: str, n_options: int) -> int | None:
    """A numbered reply ("2", "2.", " 2 ") within 1..n_options, else None."""
    match = _CHOICE.match(text.strip())
    if match is None:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= n_options else None


@dataclass(frozen=True)
class LanguageStep:
    """What to do next: set `chosen`, or send `prompt` (in `prompt_language` when
    given), or neither."""

    chosen: LanguageCode | None = None
    prompt: str | None = None
    prompt_language: LanguageCode | None = None


def answer_to_prompt(
    text: str, last_prompt: tables.Message | None
) -> LanguageStep | None:
    """The step for a reply to the pending language prompt; None if it isn't one."""
    if last_prompt is None:
        return None
    if last_prompt.template == CONFIRM:
        choice = 1 if text.strip().lower() in _YES else parse_choice(text, 2)
        if choice == 1:
            return LanguageStep(chosen=last_prompt.language)
        if choice == 2:
            return LanguageStep(prompt=MENU)
    if last_prompt.template == MENU:
        choice = parse_choice(text, len(LANGUAGES))
        if choice is not None:
            return LanguageStep(chosen=LANGUAGES[choice - 1])
    return None


def prompt_for(
    detected: LanguageCode | None, *, has_text: bool, prompt_pending: bool
) -> LanguageStep:
    """The prompt for a message that didn't answer one."""
    if detected in LANGUAGES:
        return LanguageStep(prompt=CONFIRM, prompt_language=detected)
    if prompt_pending and not has_text:
        # More photos while we wait for the pick: don't ask again.
        return LanguageStep()
    return LanguageStep(prompt=MENU)


async def last_language_prompt(user_id: UserId) -> tables.Message | None:
    messages = await reads.list_messages(user_id)
    return next(
        (
            message
            for message in reversed(messages)
            if message.direction == MessageDirection.OUT
            and message.template in _PROMPTS
        ),
        None,
    )
