"""Pacing what the orchestrator says to each user, so they can answer before the next
thing arrives (whatsapp-pipe.md → Pacing).

- One speaker at a time: an orchestrator turn and each proactive message (the
  explanation, the verdict, the post-call summary) hold the user's lock while they're
  built and sent. A reply never lands in the middle of, or repeats, a message that
  went out while it was being written.
- One numbered question at a time: a "1" must answer exactly one question. Each
  asker checks `question_open` and holds back while another is open.
- "Typing…" while the user waits on us: a turn, the fast pass on their letter, a
  lookup on official sites. It points at their latest message (and marks it read),
  so it adds nothing to the chat and writes nothing to the database. WhatsApp clears
  it after 25 s, so it's re-sent every 20 s until the work is done or its cap is up.

The pipe says which questions are open (`bind`) and records each user's latest
message (`heard`). Held in memory, like the open questions themselves.
"""

import asyncio
import contextlib
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator

from app.contracts.common import UserId
from app.relay.whatsapp import WhatsApp

QuestionOpen = Callable[[UserId], Awaitable[bool]]

# WhatsApp clears the indicator after 25 s.
TYPING_REFRESH_S = 20.0


class Conversation:
    def __init__(
        self, whatsapp: WhatsApp, typing_refresh_s: float = TYPING_REFRESH_S
    ) -> None:
        self._whatsapp = whatsapp
        self._typing_refresh_s = typing_refresh_s
        self._locks: defaultdict[UserId, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._question_open: QuestionOpen | None = None
        self._latest_sid: dict[UserId, str] = {}
        # Why each user sees "typing…", and until when (monotonic).
        self._typing: dict[UserId, dict[str, float]] = {}
        self._typing_tasks: dict[UserId, asyncio.Task[None]] = {}

    def speaking(self, user_id: UserId) -> asyncio.Lock:
        """Hold while building and sending a reply or a proactive message. Not
        reentrant: take it only where the work starts (a turn, a job reaction)."""
        return self._locks[user_id]

    def bind(self, question_open: QuestionOpen) -> None:
        """The pipe's check for an open numbered question."""
        self._question_open = question_open

    async def question_open(self, user_id: UserId) -> bool:
        return self._question_open is not None and await self._question_open(user_id)

    def heard(self, user_id: UserId, message_sid: str) -> None:
        """The user's latest message: "typing…" answers it."""
        self._latest_sid[user_id] = message_sid

    def typing(self, user_id: UserId, reason: str, max_s: float) -> None:
        """Show "typing…" until `done_typing(user_id, reason)`, for at most `max_s`.
        Several reasons can overlap; it shows while any is open."""
        self._typing.setdefault(user_id, {})[reason] = time.monotonic() + max_s
        self._cancel_typing_task(user_id)  # restart, so it shows now
        self._typing_tasks[user_id] = asyncio.create_task(self._keep_typing(user_id))

    def done_typing(self, user_id: UserId, reason: str) -> None:
        reasons = self._typing.get(user_id, {})
        reasons.pop(reason, None)
        if not reasons:
            self._typing.pop(user_id, None)
            self._cancel_typing_task(user_id)

    @contextlib.contextmanager
    def typing_while(
        self, user_id: UserId, reason: str, max_s: float
    ) -> Iterator[None]:
        self.typing(user_id, reason, max_s)
        try:
            yield
        finally:
            self.done_typing(user_id, reason)

    def is_typing(self, user_id: UserId) -> bool:
        return user_id in self._typing

    def _cancel_typing_task(self, user_id: UserId) -> None:
        task = self._typing_tasks.pop(user_id, None)
        if task is not None:
            task.cancel()

    async def _keep_typing(self, user_id: UserId) -> None:
        while True:
            now = time.monotonic()
            reasons = self._typing.get(user_id, {})
            for reason in [r for r, until in reasons.items() if until <= now]:
                del reasons[reason]
            if not reasons:
                self._typing.pop(user_id, None)
                self._typing_tasks.pop(user_id, None)
                return
            sid = self._latest_sid.get(user_id)
            if sid is not None:
                await self._whatsapp.typing(sid)
            await asyncio.sleep(
                min(self._typing_refresh_s, min(reasons.values()) - now)
            )
