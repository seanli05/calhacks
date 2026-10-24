"""Consent and the call (Plan.md → H2, P3, C8, C21, C22; Goal 6.3, 6.4).

Product rule 4, in code: a call job is queued only from the user's own numbered YES
to a consent request for that case, sent while the case is verified with an official
number, and one YES covers one call. The model can ask for consent (the turn's
`request_consent` tool) but can't start a call: only the user's reply does, through
`answer`.

The open request lives in memory, one per user. A restart forgets it, and a "1" sent
then goes to the orchestrator turn, which can ask again.

When the call job finishes, the user gets the summary, then either a new consent
request (failed, unreachable: C21) or a suggestion to close the case (resolved with no
follow-up: C22).
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.contracts import (
    CallJob,
    CallOutcome,
    CallReport,
    Component,
    Event,
    EventType,
    JobStatus,
    MessageDirection,
    VerificationStatus,
)
from app.contracts.common import CaseId, UserId
from app.db import jobs, reads, tables
from app.db.errors import UnverifiedNumber
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow
from app.orchestrator.call_status import CallStatusWatcher
from app.orchestrator.call_summary import send_call_summary
from app.orchestrator.job_watch import JobWatcher
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp, WhatsAppSendError
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

# H2's example value; Plan.md → Failure rules: past this, hang up and report failed.
MAX_HOLD_MINUTES = 60


@dataclass(frozen=True)
class PendingConsent:
    case_id: CaseId
    asked_at: datetime


class ConsentGate:
    def __init__(
        self,
        whatsapp: WhatsApp,
        translator: Translator | None,
        job_watcher: JobWatcher,
        call_status: CallStatusWatcher,
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._job_watcher = job_watcher
        self._call_status = call_status
        self._pending: dict[UserId, PendingConsent] = {}
        # Cases with a call job queued or running: no second request until it ends.
        self._calling: set[CaseId] = set()

    def pending(self, user_id: UserId) -> PendingConsent | None:
        return self._pending.get(user_id)

    async def request(
        self, user: tables.User, case_id: CaseId, *, goal_en: str | None = None
    ) -> str | None:
        """Ask the user whether to call about this case. Returns None once asked, or
        the reason (English, for the model) the call can't be offered."""
        case = await reads.get_case(case_id)
        if case is None or case.user_id != user.id:
            return f"No case {case_id} for this user."
        refusal = await self._refusal(case_id)
        if refusal is not None:
            return refusal
        brief = await reads.latest_brief(case_id)
        if brief is None:
            return "The call plan isn't ready yet."
        goal_en = goal_en or brief.brief.get("call_goal_en")
        language = user.language or "en"
        goal = await localize(self._translator, goal_en, language) if goal_en else None
        if goal is not None and goal_en is not None:
            asked = await send_template(
                self._whatsapp,
                user,
                "consent.request",
                {"goal": goal},
                values_en={"goal": goal_en},
                case_id=case_id,
            )
        else:
            asked = await send_template(
                self._whatsapp, user, "consent.request_generic", case_id=case_id
            )
        self._pending[user.id] = PendingConsent(case_id, asked.created_at)
        await _event(
            EventType.CONSENT_REQUESTED,
            user.id,
            case_id,
            "Asked the user for permission to call",
            agency=(case.fast_result or {}).get("issuer") or "USCIS",
        )
        logger.info("Consent requested user_id=%s case_id=%s", user.id, case_id)
        return None

    async def answer(
        self, user: tables.User, reply: tables.Message, choice: int
    ) -> None:
        """The user's 1 (call) or 2 (don't) to the open request. Either way the
        request is used up: a later call asks again (C21)."""
        pending = self._pending.pop(user.id, None)
        if pending is None:
            logger.error("Consent answer with no open request user_id=%s", user.id)
            return
        if choice != 1:
            await _event(
                EventType.CONSENT_DECLINED,
                user.id,
                pending.case_id,
                "The user said no to the call",
                consent_message_id=reply.id,
            )
            await send_template(
                self._whatsapp, user, "consent.declined", case_id=pending.case_id
            )
            return
        await self._start_call(user, pending, reply)

    async def _start_call(
        self, user: tables.User, pending: PendingConsent, reply: tables.Message
    ) -> None:
        """Queue the call, after checking the gate once more: things may have
        changed since the request went out."""
        case_id = pending.case_id
        refusal = await self._refusal(case_id)
        brief = await reads.latest_brief(case_id)
        if refusal is None and brief is None:
            refusal = "The call plan isn't ready yet."
        if refusal is None and not _is_yes_to(reply, user, pending):
            refusal = "The reply isn't the user's answer to this request."
        if refusal is not None or brief is None:
            logger.error(
                "Call refused user_id=%s case_id=%s: %s", user.id, case_id, refusal
            )
            await send_template(
                self._whatsapp, user, "consent.unavailable", case_id=case_id
            )
            return
        # Logged before the job exists: if the consent record can't be written,
        # there's no call.
        await _event(
            EventType.CONSENT_GIVEN,
            user.id,
            case_id,
            "The user said yes to one call",
            consent_message_id=reply.id,
        )
        since = utcnow()
        job = await jobs.enqueue(
            CallJob(
                case_id=case_id,
                user_id=user.id,
                brief_id=brief.id,
                user_language=user.language or "en",
                consent_at=reply.created_at,
                consent_message_id=reply.id,
                max_hold_minutes=MAX_HOLD_MINUTES,
            ),
            Component.ORCHESTRATOR,
            user.id,
            case_id,
        )
        self._calling.add(case_id)
        logger.info(
            "Call queued user_id=%s case_id=%s job_id=%s", user.id, case_id, job.id
        )
        self._call_status.watch(user.id, since)
        self._job_watcher.watch(job.id, self._call_finished)
        try:
            await send_template(self._whatsapp, user, "consent.given", case_id=case_id)
        except WhatsAppSendError as exc:
            logger.error("Consent ack not sent case_id=%s: %s", case_id, exc)

    async def _refusal(self, case_id: CaseId) -> str | None:
        """Why no call can be offered for this case right now, or None."""
        if case_id in self._calling:
            return "A call for this case is already in progress."
        verification = await reads.latest_verification(case_id)
        if verification is None or verification.status != VerificationStatus.VERIFIED:
            return "The letter hasn't been verified, so no call can be offered."
        try:
            await reads.official_dial_number(case_id)
        except UnverifiedNumber:
            return "There's no verified official number to call."
        return None

    async def _call_finished(self, job: tables.Job) -> None:
        case_id = job.case_id
        assert case_id is not None
        self._calling.discard(case_id)
        report = None
        if job.status == JobStatus.DONE:
            try:
                report = CallReport.model_validate(job.result)
            except ValidationError:
                logger.exception("Bad call report job_id=%s", job.id)
        else:
            logger.error("Call job failed job_id=%s: %s", job.id, job.error)
        user = await reads.get_user(job.user_id)
        if user is None:
            return
        try:
            await send_call_summary(
                self._whatsapp, self._translator, user, report, case_id
            )
            await self._after_call(user, case_id, report)
        except WhatsAppSendError as exc:
            logger.error("Post-call message not sent case_id=%s: %s", case_id, exc)

    async def _after_call(
        self, user: tables.User, case_id: CaseId, report: CallReport | None
    ) -> None:
        outcome = report.outcome if report is not None else CallOutcome.FAILED
        if outcome in (CallOutcome.FAILED, CallOutcome.USER_UNREACHABLE):
            refusal = await self.request(user, case_id)
            if refusal is not None:
                logger.info("No retry offered case_id=%s: %s", case_id, refusal)
        elif outcome == CallOutcome.RESOLVED and report and not report.followup_needed:
            await send_template(
                self._whatsapp, user, "summary.suggest_close", case_id=case_id
            )


def _is_yes_to(
    reply: tables.Message, user: tables.User, pending: PendingConsent
) -> bool:
    return (
        reply.user_id == user.id
        and reply.direction == MessageDirection.IN
        and reply.created_at >= pending.asked_at
    )


async def _event(
    event_type: EventType,
    user_id: UserId,
    case_id: CaseId,
    summary_en: str,
    **data: Any,
) -> None:
    await append_event(
        Event(
            event_id=new_id("event"),
            created_at=utcnow(),
            type=event_type,
            source=Component.ORCHESTRATOR,
            user_id=user_id,
            case_id=case_id,
            summary_en=summary_en,
            data=data,
        )
    )
