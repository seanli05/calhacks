"""First-contact language pick (Plan.md C44, replacing the Oct 23 one-tap confirm).

A first message clear enough to read sets the language at once, and the reply
confirms it in passing ("if another language is easier, just tell me"); the user
switches any time by asking (the turn's `set_language`). Only an unclear message
("ok", "hi", an emoji, mixed languages, a language we don't write in, a photo with no
text) gets the multilingual question. That question has no numbers to pick from,
but a number still works, and so does the language's name or a sentence in it.

Before, a first message got "Shall we continue in Spanish? 1 Yes / 2 Another
language", and anything but 1 or 2 got the same question again.

The pending question is read back from the message log (the user's last outbound
language template), so it survives a restart.
"""

from dataclasses import dataclass

from app.contracts import MessageDirection
from app.contracts.common import LanguageCode, UserId
from app.db import reads, tables
from app.relay.replies import parse_choice
from app.relay.templates import LANGUAGES

MENU = "language.menu"
# The retired one-tap confirm: one still pending in a user's history counts as asked.
CONFIRM = "language.confirm"
_PROMPTS = {CONFIRM, MENU}
# A reply that names a language, in any of the menu's languages. No bare codes:
# "es" and "en" are everyday Spanish words ("¿qué es…?", "en español").
_NAMES: dict[str, LanguageCode] = {
    "español": "es",
    "espanol": "es",
    "castellano": "es",
    "spanish": "es",
    "اسپانیایی": "es",
    "english": "en",
    "inglés": "en",
    "ingles": "en",
    "انگلیسی": "en",
    "دری": "fa",
    "dari": "fa",
    "فارسی": "fa",
    "farsi": "fa",
    "persian": "fa",
}
# A language's name inside a short reply ("english please", "en español"); longer
# text is read by detection instead.
_MAX_PICK_WORDS = 4
_TRIM = " .,!¡?¿؟،:;"


@dataclass(frozen=True)
class LanguageStep:
    """What to do next: set `chosen`, or send `prompt`, or neither. `guessed` means
    `chosen` came from how the user wrote, not from a pick, so the reply confirms it
    in passing."""

    chosen: LanguageCode | None = None
    guessed: bool = False
    prompt: str | None = None


def picked(text: str) -> LanguageCode | None:
    """The language a short reply picks: its menu number or its name."""
    choice = parse_choice(text, len(LANGUAGES))
    if choice is not None:
        return LANGUAGES[choice - 1]
    words = [word.strip(_TRIM) for word in text.casefold().split()]
    if not words or len(words) > _MAX_PICK_WORDS:
        return None
    named = {_NAMES[word] for word in words if word in _NAMES}
    return named.pop() if len(named) == 1 else None


def language_step(
    text: str, detected: LanguageCode | None, *, prompt_pending: bool
) -> LanguageStep:
    """The step for a message from a user with no language yet. `detected` is what
    detection read from `text` (None when unsure or not run)."""
    if text and (choice := picked(text)) is not None:
        return LanguageStep(chosen=choice)
    if detected in LANGUAGES:
        return LanguageStep(chosen=detected, guessed=True)
    if prompt_pending and not text:
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
