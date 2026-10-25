"""Noticing the deep pass and telling the user the verdict (Plan.md → R2, C18, C32;
Goal 6.2).

Research queues `research_deep` itself, so the orchestrator never learns the job's
ID. It does log `research.deep_done` with the job's ID when it finishes, so after the
explanation goes out, one watcher per case polls the user's events for that, then
reads R2 from the job. Same pattern as the call-status watcher; held in memory, so a
restart forgets it.

- Verified: say so, and nothing more. A call is offered only when the user's
  messages show they need one (the turn's `request_consent`), never because the
  letter checked out: most letters need no call.
- Verified with no official number to call: say so, and that no call is needed.
- Suspicious: warn with the red flags; never offer a call.
- Unknown: explain, no call offer, and ask what the user wants.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import DeepResult, EventType, JobStatus, VerificationStatus
from app.contracts.common import CaseId, UserId
from app.db import reads, tables
from app.orchestrator.conversation import Conversation
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp, WhatsAppSendError
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0
# Plan.md's target is 1–3 minutes; past this the case stops being watched (Plan.md
# has no failure rule for a deep pass that never finishes yet).
MAX_WATCH_S = 15 * 60.0
_TICK = timedelta(microseconds=1)


class Verdicts:
    def __init__(
        self,
        whatsapp: WhatsApp,
        translator: Translator | None,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_watch_s: float = MAX_WATCH_S,
        *,
        conversation: Conversation,
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._conversation = conversation
        self._poll_interval_s = poll_interval_s
        self._max_watch_s = max_watch_s
        self._watching: dict[CaseId, asyncio.Task[None]] = {}
        self._watching_users: dict[CaseId, UserId] = {}

    def watch(self, user_id: UserId, case_id: CaseId, since: datetime) -> None:
        """Tell the user the verdict of the case's next deep pass to finish after
        `since`. Watching a case twice does nothing."""
        task = self._watching.get(case_id)
        if task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(user_id, case_id, since))
        self._watching[case_id] = task
        self._watching_users[case_id] = user_id
        task.add_done_callback(lambda _: self._forget(case_id))

    def _forget(self, case_id: CaseId) -> None:
        self._watching.pop(case_id, None)
        self._watching_users.pop(case_id, None)

    def is_watching(self, case_id: CaseId) -> bool:
        return case_id in self._watching

    def watching_for(self, user_id: UserId) -> bool:
        """A verdict is still coming for one of the user's letters."""
        return user_id in self._watching_users.values()

    async def _run(self, user_id: UserId, case_id: CaseId, since: datetime) -> None:
        deadline = time.monotonic() + self._max_watch_s
        while time.monotonic() < deadline:
            try:
                deep = await self._finished_deep(user_id, case_id, since)
            except (SQLAlchemyError, OSError):
                logger.exception("Verdict: reading events failed case_id=%s", case_id)
                deep = None
            if deep is not None:
                await self._tell(user_id, case_id, deep)
                return
            await asyncio.sleep(self._poll_interval_s)
        logger.warning("Verdict: no deep pass finished case_id=%s", case_id)

    async def _finished_deep(
        self, user_id: UserId, case_id: CaseId, since: datetime
    ) -> tables.Job | None:
        # `since` is exclusive and clocks tick coarsely: read from just before it.
        for event in await reads.list_events(user_id, since=since - _TICK):
            if event.type != EventType.RESEARCH_DEEP_DONE or event.case_id != case_id:
                continue
            if event.job_id is None:
                logger.error("research.deep_done without job_id case_id=%s", case_id)
                continue
            job = await reads.get_job(event.job_id)
            if job is not None and job.status in (JobStatus.DONE, JobStatus.FAILED):
                return job
        return None

    async def _tell(self, user_id: UserId, case_id: CaseId, job: tables.Job) -> None:
        user = await reads.get_user(user_id)
        if user is None:
            return
        if job.status == JobStatus.FAILED:
            # Plan.md has no failure rule for a failed deep pass yet (Goal 8).
            logger.error("Deep pass failed case_id=%s job_id=%s", case_id, job.id)
            return
        try:
            deep = DeepResult.model_validate(job.result)
        except ValidationError:
            logger.exception("Bad R2 case_id=%s job_id=%s", case_id, job.id)
            return
        async with self._conversation.speaking(user.id):
            try:
                await self.react(user, deep)
            except WhatsAppSendError as exc:
                logger.error("Verdict not sent case_id=%s: %s", case_id, exc)

    async def react(self, user: tables.User, deep: DeepResult) -> None:
        """R2's three branches (Plan.md → R2, Failure rules)."""
        status = deep.verification.status
        case_id = deep.case_id
        logger.info("Verdict case_id=%s status=%s", case_id, status)
        if status == VerificationStatus.VERIFIED:
            if not deep.call_recommended:
                await self._send(user, "verification.verified_no_call", case_id)
                return
            await self._send(user, "verification.verified", case_id)
        elif status == VerificationStatus.SUSPICIOUS:
            await self._warn(user, deep)
        elif status == VerificationStatus.UNKNOWN:
            await self._send(user, "verification.unknown", case_id)

    async def _warn(self, user: tables.User, deep: DeepResult) -> None:
        flags_en = "\n".join(f"- {flag}" for flag in deep.verification.red_flags)
        language = user.language or "en"
        flags = (
            await localize(self._translator, flags_en, language) if flags_en else None
        )
        if flags is None or not flags_en:
            await self._send(user, "verification.suspicious_generic", deep.case_id)
            return
        await send_template(
            self._whatsapp,
            user,
            "verification.suspicious",
            {"red_flags": flags},
            values_en={"red_flags": flags_en},
            case_id=deep.case_id,
        )

    async def _send(self, user: tables.User, template: str, case_id: CaseId) -> None:
        await send_template(self._whatsapp, user, template, case_id=case_id)
