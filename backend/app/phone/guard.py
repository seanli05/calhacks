"""C35 at the line: nothing the agent says or keys may carry the applicant's identifiers.

`menu.check_action` already rejects refs and digit runs in each model action. This
is the last check, against the case's real values, on everything that actually
leaves, and it reads the digits of the whole call as one stream, so an identifier
fed out a few digits at a time is caught too. A blocked step raises
`BlockedIdentifier` and nothing is sent.

Limits: it matches digits (written or spoken as "one", "two", …), so a date said
as "March fourteenth" gets through. The menu guard and prompt cover that side.
"""

import re
from collections.abc import AsyncIterator, Iterable

from app.contracts.common import CallId, CaseId, UserId
from app.phone.line import LineEvent
from app.phone.ports import Telephony

GUARDED_REFS = ("receipt_number", "a_number", "date_of_birth")
"""The refs C35 names. `adapters.load_blocked_values` resolves them per case."""

_MIN_DIGITS = 6
"""A value with fewer digits is matched as text instead, so menu digits like "2"
can't trip it."""
_KEYS = re.compile(r"^[0-9*#]+$")
_TOKEN = re.compile(r"\d|[a-z]+")
_DIGIT_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}


class BlockedIdentifier(Exception):
    """The step would have sent an identifier. The message names the rule, never
    the value, so it's safe to log."""


def spoken_digits(text: str) -> str:
    """The digits in `text` in order, counting digit words ("one") as digits."""
    tokens = _TOKEN.findall(text.lower())
    return "".join(
        token if token.isdigit() else _DIGIT_WORDS.get(token, "") for token in tokens
    )


def _alnum(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


class GuardedTelephony:
    """Wraps any `Telephony`; checks `say` and `press_keys`, passes the rest through."""

    def __init__(self, inner: Telephony, blocked_values: Iterable[str]) -> None:
        self._inner = inner
        self._digit_values: list[str] = []
        self._text_values: list[str] = []
        for value in blocked_values:
            digits = spoken_digits(value)
            if len(digits) >= _MIN_DIGITS:
                self._digit_values.append(digits)
            elif len(_alnum(value)) >= 4:
                self._text_values.append(_alnum(value))
        self._sent_digits = ""

    def __repr__(self) -> str:
        return f"GuardedTelephony({self._inner!r})"

    def _check(self, text: str) -> None:
        sent = self._sent_digits + spoken_digits(text)
        if any(value in sent for value in self._digit_values):
            raise BlockedIdentifier("an identifier's digits would go out (C35)")
        alnum = _alnum(text)
        if any(value in alnum for value in self._text_values):
            raise BlockedIdentifier("an identifier would go out (C35)")
        self._sent_digits = sent

    async def dial_agency(self, call_id: CallId, case_id: CaseId) -> str:
        return await self._inner.dial_agency(call_id, case_id)

    async def say(self, text: str) -> None:
        self._check(text)
        await self._inner.say(text)

    async def press_keys(self, digits: str) -> None:
        if not _KEYS.match(digits):
            raise ValueError("keys must be 0-9, * or #")
        self._check(digits)
        await self._inner.press_keys(digits)

    async def ring_user(self, call_id: CallId, user_id: UserId) -> None:
        await self._inner.ring_user(call_id, user_id)

    async def connect_user(self) -> None:
        await self._inner.connect_user()

    async def hang_up(self) -> None:
        await self._inner.hang_up()

    def events(self) -> AsyncIterator[LineEvent]:
        return self._inner.events()
