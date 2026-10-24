"""Sends menu choices on the line (C37): speak first, keypad when a step won't take speech.

A press is spoken as the digit word ("two"): menus that offer "press or say 2" take
the digit, and a spoken label can fall outside a strict speech grammar. A step is
treated as keypad-only when its prompt says so ("using your keypad", "followed by
pound"), or when the menu answers a spoken press with a no-match or no-input
reprompt or the same prompt again. Keypad mode is then sticky for the rest of that
menu tree (keypad-only menus usually are all keypad, and C37 batches digits); the
runner resets it when the line goes to hold.

Everything goes out through the `Telephony` it's given, which the runner makes sure
is a `GuardedTelephony` (C35).
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.phone.menu import MenuTurn, PressAction, SayAction, WaitAction, find_repeats
from app.phone.ports import Telephony

_KEY_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "*": "star",
    "#": "pound",
}
_KEYPAD_ONLY = re.compile(
    r"\b(?:key\s?pad|touch[- ]?tone)\b"
    r"|\bfollowed\s+by\s+(?:the\s+)?(?:pound|hash)\b"
    r"|\busing\s+(?:the\s+|your\s+)?(?:phone'?s?\s+)?(?:keys|buttons)\b",
    re.IGNORECASE,
)
_NO_MATCH = re.compile(
    r"\b(?:sorry|didn'?t|did\s+not)\s+(?:\w+\s+){0,2}(?:get|catch|hear|understand|receive)"
    r"|\bnot\s+(?:a\s+)?valid\b|\binvalid\b|\btry\s+again\b"
    r"|\bno\s+(?:selection|entry|input|response)\b",
    re.IGNORECASE,
)
"""How menus say they didn't take an answer: no-match and no-input wording."""


def spoken_keys(digits: str) -> str:
    """ "2" -> "two", "*" -> "star", "12" -> "one two"."""
    return " ".join(_KEY_WORDS[key] for key in digits)


def says_keypad_only(heard: str) -> bool:
    return _KEYPAD_ONLY.search(heard) is not None


def sounds_like_reprompt(heard: str, earlier_prompt: str) -> bool:
    """The menu didn't take the last answer: it says so, or repeats the prompt."""
    if _NO_MATCH.search(heard):
        return True
    earlier = MenuTurn(
        heard=earlier_prompt, action=WaitAction(kind="wait", reason_en="Earlier prompt")
    )
    return bool(find_repeats(heard, [earlier]))


@dataclass(frozen=True)
class Sent:
    via: Literal["speech", "keys"]
    out: str
    """What went out: the words spoken or the keys pressed. Observer only."""


class MenuExecutor:
    """One call's menu output, and whether the current menu tree needs the keypad."""

    def __init__(self, line: Telephony) -> None:
        self._line = line
        self.keypad = False
        self._spoken_press_prompt: str | None = None

    def reset(self) -> None:
        """A new menu tree (after hold): try speech again."""
        self.keypad = False
        self._spoken_press_prompt = None

    def observe(self, heard: str) -> bool:
        """Call on each menu utterance before deciding. Returns True if it just
        switched this tree to keypad mode."""
        prompt, self._spoken_press_prompt = self._spoken_press_prompt, None
        if self.keypad:
            return False
        if says_keypad_only(heard) or (
            prompt is not None and sounds_like_reprompt(heard, prompt)
        ):
            self.keypad = True
            return True
        return False

    async def press(self, action: PressAction, prompt: str) -> Sent:
        """`prompt` is what the menu said before this press, to spot a reprompt."""
        if self.keypad:
            await self._line.press_keys(action.digits)
            return Sent("keys", action.digits)
        words = spoken_keys(action.digits)
        await self._line.say(words)
        self._spoken_press_prompt = prompt
        return Sent("speech", words)

    async def say(self, action: SayAction) -> Sent:
        await self._line.say(action.text)
        return Sent("speech", action.text)
