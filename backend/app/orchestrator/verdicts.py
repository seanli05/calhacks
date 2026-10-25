"""Noticing the deep pass and telling the user the verdict (Plan.md → R2, C18, C32;
Goal 6.2).

Research queues `research_deep` itself, so the orchestrator never learns the job's
ID. It does log `research.deep_done` with the job's ID when it finishes, so once the
letter is read, one watcher per case polls the user's events for that, then reads R2
from the job. Same pattern as the call-status watcher; held in memory, so a restart
forgets it.

C45: the letter is checked before it's explained. The watcher holds the explanation
(`explain`) and sends it with the verdict, in one message, as the lead of the
verdict's template:
- Verified and a call recommended: the explanation, then "it's genuine" and the
  consent request. If another numbered question is open, the request waits until the
  user has answered (conversation.py).
- Verified, no call needed: the explanation, then "it's genuine, no need to call".
- Unknown, or the deep pass failed: the explanation, then a gentle caution.
- Suspicious: the warning with the red flags, never the explanation or a call.
If no verdict comes within `explain_after_s`, the explanation goes out with "still
checking, don't pay or call yet", and the verdict follows alone when it comes.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from functools import partial

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import DeepResult, EventType, JobStatus, VerificationStatus
from app.contracts.common import CaseId, UserId
from app.db import reads, tables
from app.orchestrator.consent import ConsentGate
from app.orchestrator.conversation import Conversation
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp, WhatsAppSendError
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0
# Plan.md's target is 1–3 minutes; past this the case stops being watched (Plan.md
# has no failure rule for a deep pass that never finishes yet).
MAX_WATCH_S = 15 * 60.0
# C45: how long the explanation waits for the verdict.
EXPLAIN_AFTER_S = 60.0
_TICK = timedelta(microseconds=1)
_TYPING = "verdict"

# Builds the letter's explanation in the user's language, and its English.
Explain = Callable[[tables.User], Awaitable[tuple[str, str]]]


class Verdicts:
    def __init__(
        self,
        whatsapp: WhatsApp,
        translator: Translator | None,
        consent: ConsentGate,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_watch_s: float = MAX_WATCH_S,
        *,
        conversation: Conversation,
        explain_after_s: float = EXPLAIN_AFTER_S,
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._consent = consent
        self._conversation = conversation
        self._poll_interval_s = poll_interval_s
        self._max_watch_s = max_watch_s
        self._explain_after_s = explain_after_s
        self._watching: dict[CaseId, asyncio.Task[None]] = {}
        self._watching_users: dict[CaseId, UserId] = {}
        # The explanation each case still owes the user.
        self._explain: dict[CaseId, Explain] = {}

    def watch(
        self,
        user_id: UserId,
        case_id: CaseId,
        since: datetime,
        *,
        explain: Explain | None = None,
    ) -> None:
        """Tell the user the verdict of the case's next deep pass to finish after
        `since`, after `explain`'s explanation in the same message. Watching a case
        twice keeps one watcher; a new `explain` (the letter was read again)
        replaces the one still owed."""
        if explain is not None:
            self._explain[case_id] = explain
            self._conversation.typing(user_id, _TYPING, self._explain_after_s)
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
        self._explain.pop(case_id, None)

    def is_watching(self, case_id: CaseId) -> bool:
        return case_id in self._watching

    def watching_for(self, user_id: UserId) -> bool:
        """A verdict is still coming for one of the user's letters."""
        return user_id in self._watching_users.values()

    async def _run(self, user_id: UserId, case_id: CaseId, since: datetime) -> None:
        start = time.monotonic()
        while time.monotonic() < start + self._max_watch_s:
            try:
                deep = await self._finished_deep(user_id, case_id, since)
            except (SQLAlchemyError, OSError):
                logger.exception("Verdict: reading events failed case_id=%s", case_id)
                deep = None
            if deep is not None:
                await self._tell(user_id, case_id, deep)
                return
            if (
                case_id in self._explain
                and time.monotonic() >= start + self._explain_after_s
            ):
                await self._explain_while_checking(user_id, case_id)
            await asyncio.sleep(self._poll_interval_s)
        logger.warning("Verdict: no deep pass finished case_id=%s", case_id)

    async def _explain_while_checking(self, user_id: UserId, case_id: CaseId) -> None:
        """C45: no verdict in time; explain now, with a caution not to pay or call
        yet. The verdict follows alone."""
        explain = self._explain.pop(case_id)
        self._conversation.done_typing(user_id, _TYPING)
        user = await reads.get_user(user_id)
        if user is None:
            return
        logger.info("Explaining before the verdict case_id=%s", case_id)
        async with self._conversation.speaking(user.id):
            try:
                lead = await explain(user)
                await self._send(user, "letter.still_checking", case_id, lead)
            except WhatsAppSendError as exc:
                logger.error("Explanation not sent case_id=%s: %s", case_id, exc)

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
        explain = self._explain.pop(case_id, None)
        self._conversation.done_typing(user_id, _TYPING)
        user = await reads.get_user(user_id)
        if user is None:
            return
        deep = None
        if job.status == JobStatus.FAILED:
            logger.error("Deep pass failed case_id=%s job_id=%s", case_id, job.id)
        else:
            try:
                deep = DeepResult.model_validate(job.result)
            except ValidationError:
                logger.exception("Bad R2 case_id=%s job_id=%s", case_id, job.id)
        async with self._conversation.speaking(user.id):
            try:
                lead = await explain(user) if explain is not None else None
                if deep is None:
                    # No verdict will come: as for unknown (C45).
                    await self._send(user, "verification.unknown", case_id, lead)
                else:
                    await self.react(user, deep, lead)
            except WhatsAppSendError as exc:
                logger.error("Verdict not sent case_id=%s: %s", case_id, exc)

    async def react(
        self, user: tables.User, deep: DeepResult, lead: tuple[str, str] | None = None
    ) -> None:
        """R2's three branches (Plan.md → R2, Failure rules), after `lead` (the
        letter's explanation, if it hasn't gone out yet) in the same message. A
        suspicious letter is never explained."""
        status = deep.verification.status
        case_id = deep.case_id
        logger.info("Verdict case_id=%s status=%s", case_id, status)
        if status == VerificationStatus.VERIFIED:
            if not deep.call_recommended:
                await self._send(user, "verification.verified_no_call", case_id, lead)
                return
            await self._verified(user, deep, lead)
        elif status == VerificationStatus.SUSPICIOUS:
            await self._warn(user, deep)
        elif status == VerificationStatus.UNKNOWN:
            await self._send(user, "verification.unknown", case_id, lead)

    async def _verified(
        self, user: tables.User, deep: DeepResult, lead: tuple[str, str] | None
    ) -> None:
        case_id = deep.case_id
        if await self._conversation.question_open(user.id):
            await self._send(user, "verification.verified", case_id, lead)
            self._conversation.send_when_free(
                user.id, partial(self._request_consent, user.id, deep)
            )
            logger.info("Consent request waits for an answer case_id=%s", case_id)
            return
        refusal = await self._consent.request(
            user, case_id, goal_en=deep.call_goal_en, verified=True, lead=lead
        )
        if refusal is not None:
            logger.error("Consent not requested case_id=%s: %s", case_id, refusal)
            await self._send(user, "verification.verified", case_id, lead)

    async def _request_consent(self, user_id: UserId, deep: DeepResult) -> None:
        """The consent request that waited for another question's answer."""
        user = await reads.get_user(user_id)  # the language may have changed
        if user is None:
            return
        refusal = await self._consent.request(
            user, deep.case_id, goal_en=deep.call_goal_en
        )
        if refusal is not None:
            logger.error("Consent not requested case_id=%s: %s", deep.case_id, refusal)

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

    async def _send(
        self,
        user: tables.User,
        template: str,
        case_id: CaseId,
        lead: tuple[str, str] | None = None,
    ) -> None:
        await send_template(self._whatsapp, user, template, case_id=case_id, lead=lead)
