"""A fake phone agent (person 2's Goal 3.5): plays one scripted call so ask_user and
the call-status messages can be tried on a real phone before the real phone agent
(person 4) exists. It never dials anything.

It stands in for research and the phone agent, so it writes their rows (a case, a
brief, a call) through their writer modules. That's the only reason this package
imports `writes.research` and `writes.phone`; nothing else of person 2's does.

Safety (rules 2 and 4): the call job it needs (for the `calls` foreign key) is failed
the moment it's created so no phone worker runs it, and the case is brand new with no
verification, so `official_dial_number` refuses it even if one did. The consent
pointer references a labelled dev note, never a made-up "YES".
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.contracts import (
    AskUserRequest,
    CallJob,
    CallState,
    Component,
    Event,
    EventType,
    MessageDirection,
    MessageSender,
)
from app.contracts.common import CallId, CaseId, UserId
from app.db import jobs, tables
from app.db.events import append_event
from app.db.ids import new_id
from app.db.messages import append_message
from app.db.tables import utcnow
from app.db.writes import phone, research
from app.orchestrator.call_status import CallStatusWatcher
from app.relay.ask_user import AskUser

logger = logging.getLogger(__name__)

MENU_OPTIONS = ["Speak to a representative about an appointment", "Case status"]


@dataclass(frozen=True)
class Pacing:
    """Seconds between the scripted steps. The on-hold events come faster than the
    10-minute limit on purpose: only the first should reach the user."""

    step_s: float = 3.0
    on_hold_count: int = 3
    ask_timeout_s: int = 45


async def run_fake_call(
    user: tables.User,
    ask_user: AskUser,
    call_status: CallStatusWatcher,
    pacing: Pacing | None = None,
) -> None:
    """Dialing → menu → ask_user → on hold ×N → human → joined → ended → case closed."""
    pacing = pacing or Pacing()
    started = utcnow()
    case_id, call_id = await _create_rows(user)
    logger.info("Fake call started user_id=%s call_id=%s", user.id, call_id)
    # What the orchestrator will do when it queues a real call job (Goal 6.3).
    call_status.watch(user.id, since=started)
    emit = _Emitter(user.id, case_id, call_id)

    await emit(EventType.CALL_DIALING, "Dialing USCIS (fake call)", agency="USCIS")
    await asyncio.sleep(pacing.step_s)
    await phone.set_call_state(call_id, CallState.MENU)
    await emit(EventType.CALL_MENU_HEARD, "Heard the phone menu (fake call)")
    reply = await ask_user.ask(
        AskUserRequest(
            question_id=new_id("question"),
            call_id=call_id,
            template="menu_choice",
            options_en=MENU_OPTIONS,
            default_option=1,
            timeout_s=pacing.ask_timeout_s,
        )
    )
    await emit(
        EventType.CALL_MENU_CHOICE,
        f"Chose menu option {reply.choice} (fake call)",
        digit=str(reply.choice),
    )
    await phone.set_call_state(call_id, CallState.HOLD)
    for _ in range(pacing.on_hold_count):
        await asyncio.sleep(pacing.step_s)
        await emit(EventType.CALL_ON_HOLD, "On hold (fake call)", agency="USCIS")
    await asyncio.sleep(pacing.step_s)
    await phone.set_call_state(call_id, CallState.HUMAN_DETECTED)
    await emit(
        EventType.CALL_HUMAN_DETECTED, "A person answered (fake call)", agency="USCIS"
    )
    await asyncio.sleep(pacing.step_s)
    await emit(EventType.CALL_USER_JOINED, "User joined (fake call)", agency="USCIS")
    await asyncio.sleep(pacing.step_s)
    await phone.set_call_state(call_id, CallState.ENDED)
    await emit(EventType.CALL_ENDED, "Call ended (fake call)", minutes=1)
    # Close the throwaway case so it doesn't look like a real open letter (C22).
    await emit(
        EventType.CASE_CLOSED,
        "Closed the fake call's case",
        source=Component.ORCHESTRATOR,
    )
    logger.info("Fake call finished user_id=%s call_id=%s", user.id, call_id)


async def _create_rows(user: tables.User) -> tuple[CaseId, CallId]:
    case = await research.create_case(new_id("case"), user.id, [])
    brief = await research.save_brief(
        case.id, {"call_goal_en": "Dev fake call"}, "[dev] fake call, nothing is dialed"
    )
    note = await append_message(
        user.id,
        MessageDirection.OUT,
        MessageSender.RELAY,
        "[dev] Fake call started from /dev/fake-call. Not a consent record.",
        user.language or "en",
        case_id=case.id,
    )
    job = await jobs.enqueue(
        CallJob(
            case_id=case.id,
            user_id=user.id,
            brief_id=brief.id,
            user_language=user.language or "en",
            consent_at=utcnow(),
            consent_message_id=note.id,
            max_hold_minutes=1,
        ),
        Component.ORCHESTRATOR,
        user.id,
        case.id,
    )
    await jobs.fail(job.id, "dev fake call: never run, nothing is dialed")
    call = await phone.create_call(case.id, job.id, brief.id, note.id)
    return case.id, call.id


class _Emitter:
    """Logs events the way the phone agent will: every call event carries call_id."""

    def __init__(self, user_id: UserId, case_id: CaseId, call_id: CallId) -> None:
        self._user_id = user_id
        self._case_id = case_id
        self._call_id = call_id

    async def __call__(
        self,
        event_type: EventType,
        summary_en: str,
        source: Component = Component.PHONE_AGENT,
        **data: Any,
    ) -> None:
        await append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=event_type,
                source=source,
                user_id=self._user_id,
                case_id=self._case_id,
                call_id=self._call_id,
                summary_en=summary_en,
                data=data,
            )
        )
