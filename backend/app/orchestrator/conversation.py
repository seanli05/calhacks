"""Pacing what the orchestrator says to each user, so they can answer before the next
thing arrives (whatsapp-pipe.md → Pacing).

- One speaker at a time: an orchestrator turn and each proactive message (the
  explanation, the verdict, the post-call summary) hold the user's lock while they're
  built and sent. A reply never lands in the middle of, or repeats, a message that
  went out while it was being written.
- One numbered question at a time: a "1" must answer exactly one question. A
  proactive question that comes due while another is open waits, and goes out once
  the user has answered.

The pipe says which questions are open (`bind`) and sends what waited (`flush`) after
each message it routes. Held in memory, like the open questions themselves.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from app.contracts.common import UserId

logger = logging.getLogger(__name__)

QuestionOpen = Callable[[UserId], Awaitable[bool]]
Send = Callable[[], Awaitable[None]]


class Conversation:
    def __init__(self) -> None:
        self._locks: defaultdict[UserId, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._question_open: QuestionOpen | None = None
        self._waiting: dict[UserId, Send] = {}

    def speaking(self, user_id: UserId) -> asyncio.Lock:
        """Hold while building and sending a reply or a proactive message. Not
        reentrant: take it only where the work starts (a turn, a job reaction)."""
        return self._locks[user_id]

    def bind(self, question_open: QuestionOpen) -> None:
        """The pipe's check for an open numbered question."""
        self._question_open = question_open

    async def question_open(self, user_id: UserId) -> bool:
        return self._question_open is not None and await self._question_open(user_id)

    def send_when_free(self, user_id: UserId, send: Send) -> None:
        """Send once no question is open. One waits per user; a newer one replaces
        it."""
        if user_id in self._waiting:
            logger.info("Waiting question replaced user_id=%s", user_id)
        self._waiting[user_id] = send

    def is_waiting(self, user_id: UserId) -> bool:
        return user_id in self._waiting

    async def flush(self, user_id: UserId) -> None:
        """Send what waited, if no question is open now."""
        if user_id not in self._waiting or await self.question_open(user_id):
            return
        async with self.speaking(user_id):
            send = self._waiting.pop(user_id, None)
            if send is not None:
                await send()
