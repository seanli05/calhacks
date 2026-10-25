"""Call-status messages to the user (Plan.md → P2, C36).

The phone agent logs every call event to `events`, unfiltered. The orchestrator
decides which reach the user, by fixed rules (code, not a model call), and sends them
as relay templates:

- `call.human_detected`: always, at once (the user has 30 s to pick up).
- `call.dialing`, `call.user_unreachable`: once per call. No `call.dialing` after the
  user's YES: `consent.given` already says we're calling.
- `call.user_dialed`: only when the applicant is rung again after a missed ring;
  the first ring is covered by `call.human_detected`.
- `call.on_hold`: at most once every 10 minutes per call.
- Anything else: dashboard only.

Nothing notifies us of new events, so a watcher polls the user's events about once a
second from when the call job is queued until `call.ended`. The phone agent creates
the call (and its ID) only when it picks up the job (C7), so the watcher follows the
user, not a call ID. Watchers and throttle state live in memory: a server restart
mid-call stops status messages for that call.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy.exc import SQLAlchemyError

from app.contracts import USER_MESSAGING_EVENTS, Event, EventType
from app.contracts.common import UserId
from app.db import reads, tables
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp, WhatsAppSendError, get_whatsapp

logger = logging.getLogger(__name__)

ON_HOLD_EVERY = timedelta(minutes=10)
POLL_INTERVAL_S = 1.0
# A watcher that never sees `call.ended` (the call job failed, say) stops after this.
MAX_WATCH_S = 3 * 60 * 60.0
_TICK = timedelta(microseconds=1)

# Each event that may message the user has a template of the same name.
_TEMPLATES = {event_type: str(event_type) for event_type in USER_MESSAGING_EVENTS}


@dataclass
class _CallSent:
    dialing: bool = False
    unreachable: bool = False
    rings: int = 0
    last_on_hold: datetime | None = None


class StatusRules:
    """C36's rules for one watched user, keyed per call. Pure: no I/O."""

    def __init__(
        self, on_hold_every: timedelta = ON_HOLD_EVERY, *, announce_dialing: bool = True
    ) -> None:
        """Without `announce_dialing`, the user already knows we're calling."""
        self._on_hold_every = on_hold_every
        self._announce_dialing = announce_dialing
        self._calls: dict[str, _CallSent] = {}

    def template_for(self, event: Event) -> str | None:
        """The template to send for `event`, or None if the user shouldn't hear
        about it. Call this once per event, in order."""
        if event.type not in USER_MESSAGING_EVENTS:
            return None
        # The phone agent sets call_id on call events; the user is a fallback key.
        sent = self._calls.setdefault(
            event.call_id or event.user_id,
            _CallSent(dialing=not self._announce_dialing),
        )
        if event.type == EventType.CALL_DIALING:
            if sent.dialing:
                return None
            sent.dialing = True
        elif event.type == EventType.CALL_USER_UNREACHABLE:
            if sent.unreachable:
                return None
            sent.unreachable = True
        elif event.type == EventType.CALL_USER_DIALED:
            sent.rings += 1
            if sent.rings == 1:
                return None
        elif event.type == EventType.CALL_ON_HOLD:
            last = sent.last_on_hold
            if last is not None and event.created_at - last < self._on_hold_every:
                return None
            sent.last_on_hold = event.created_at
        return _TEMPLATES[event.type]


class CallStatusWatcher:
    def __init__(
        self,
        whatsapp: WhatsApp,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_watch_s: float = MAX_WATCH_S,
    ) -> None:
        self._whatsapp = whatsapp
        self._poll_interval_s = poll_interval_s
        self._max_watch_s = max_watch_s
        self._watching: dict[UserId, asyncio.Task[None]] = {}

    def watch(
        self, user_id: UserId, since: datetime, *, announce_dialing: bool = True
    ) -> None:
        """Relay the status of the user's next call: events at or after `since`,
        until `call.ended`. Call it with the time from just before the call job is
        queued (Goal 6.3). A second call while already watching does nothing.
        `announce_dialing=False` when the user was just told we're calling."""
        task = self._watching.get(user_id)
        if task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(user_id, since, announce_dialing))
        self._watching[user_id] = task
        task.add_done_callback(lambda _: self._watching.pop(user_id, None))

    def is_watching(self, user_id: UserId) -> bool:
        return user_id in self._watching

    async def _run(
        self, user_id: UserId, since: datetime, announce_dialing: bool
    ) -> None:
        user = await reads.get_user(user_id)
        if user is None:
            logger.error("Call status: no user %s", user_id)
            return
        rules = StatusRules(announce_dialing=announce_dialing)
        seen: set[str] = set()
        deadline = time.monotonic() + self._max_watch_s
        while time.monotonic() < deadline:
            try:
                # `since` is exclusive, and clocks tick coarsely (about 15 ms on
                # Windows), so events can share a timestamp: read from just before
                # the last one and skip what's already handled.
                events = await reads.list_events(user_id, since=since - _TICK)
            except (SQLAlchemyError, OSError):
                logger.exception(
                    "Call status: reading events failed user_id=%s", user_id
                )
                events = []
            for event in events:
                if event.event_id in seen:
                    continue
                seen.add(event.event_id)
                since = max(since, event.created_at)
                if event.type == EventType.CALL_ENDED:
                    return
                template = rules.template_for(event)
                if template is not None:
                    await self._send(user, event, template)
            await asyncio.sleep(self._poll_interval_s)
        logger.warning(
            "Call status: stopped watching user_id=%s (no call.ended)", user_id
        )

    async def _send(self, user: tables.User, event: Event, template: str) -> None:
        try:
            await send_template(self._whatsapp, user, template, case_id=event.case_id)
        except WhatsAppSendError as exc:
            logger.error(
                "Call status %s not sent call_id=%s: %s", template, event.call_id, exc
            )


@lru_cache
def get_call_status() -> CallStatusWatcher:
    return CallStatusWatcher(get_whatsapp())
