"""Group photos into letters (C20, team decision Oct 23).

WhatsApp sends each photo of a multi-select as its own webhook, a second or two
apart. A batch closes once no photo has arrived for the quiet window, and becomes
one document. A photo that arrives after research has started is held until the
user says whether it's another page or a new letter.

State is in memory: one process serves every webhook. A restart drops open batches,
but the photos themselves are already saved in `media`.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

from app.contracts.common import DocumentId, MediaId, UserId

logger = logging.getLogger(__name__)

PHOTO_QUIET_WINDOW_S = 6.0

OnBatch = Callable[[UserId, list[MediaId]], Awaitable[None]]


@dataclass
class _Batch:
    media_ids: list[MediaId] = field(default_factory=list)
    timer: asyncio.Task[None] | None = None


@dataclass
class PendingPages:
    """Photos waiting on "same letter or new?"; `document_id` is the letter they'd
    join."""

    document_id: DocumentId
    media_ids: list[MediaId]


class PhotoBatcher:
    def __init__(
        self, on_batch: OnBatch, quiet_window_s: float = PHOTO_QUIET_WINDOW_S
    ) -> None:
        self._on_batch = on_batch
        self._quiet_window_s = quiet_window_s
        self._batches: dict[UserId, _Batch] = {}
        self._pending: dict[UserId, PendingPages] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def is_open(self, user_id: UserId) -> bool:
        return user_id in self._batches

    def add(
        self, user_id: UserId, media_ids: list[MediaId], *, hold: bool = False
    ) -> None:
        """Add photos to the user's open batch (opening one if needed) and restart
        the quiet window. `hold` keeps the batch open until `release`, for photos
        sent before the user has picked a language."""
        batch = self._batches.setdefault(user_id, _Batch())
        batch.media_ids.extend(media_ids)
        if batch.timer is not None:
            batch.timer.cancel()
            batch.timer = None
        if not hold:
            batch.timer = self._spawn(self._close_when_quiet(user_id))

    def release(self, user_id: UserId) -> None:
        """Start the quiet window on a held batch."""
        batch = self._batches.get(user_id)
        if batch is not None and batch.timer is None:
            batch.timer = self._spawn(self._close_when_quiet(user_id))

    def hold_for_answer(
        self, user_id: UserId, document_id: DocumentId, media_ids: list[MediaId]
    ) -> None:
        pending = self._pending.setdefault(user_id, PendingPages(document_id, []))
        pending.media_ids.extend(media_ids)

    def pending(self, user_id: UserId) -> PendingPages | None:
        return self._pending.get(user_id)

    def take_pending(self, user_id: UserId) -> PendingPages | None:
        return self._pending.pop(user_id, None)

    def _spawn(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        # The loop holds tasks weakly; keep a reference until each one finishes.
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _close_when_quiet(self, user_id: UserId) -> None:
        await asyncio.sleep(self._quiet_window_s)
        # Popped before any await, so a photo arriving from here on opens a new
        # batch instead of cancelling this one mid-write.
        batch = self._batches.pop(user_id)
        try:
            await self._on_batch(user_id, batch.media_ids)
        except (SQLAlchemyError, OSError):
            logger.exception(
                "Closing photo batch failed user_id=%s pages=%d",
                user_id,
                len(batch.media_ids),
            )
