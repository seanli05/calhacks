"""Ports: the phone agent's boundary with everything outside its own logic.

The call runner sees only these Protocols, bundled per call in `CallDeps`. Real
adapters are in `adapters.py`; fakes for tests and the simulator are in `fakes.py`.
Some rules hold because no port can express the bad action:

- Rule 2: no method takes a phone number. `Telephony` adapters get the verified
  official number (and the user's number, C6) from a `NumberSource` at dial time,
  and the runner never holds a `NumberSource`.
- Rule 4: dialing needs a `call_id`, which only `CallStore.create_call` mints, from
  a `CallJob` that carries `consent_message_id` (C8).
- C35: nothing here resolves a `<ref:…>`. Only the guard (`guard.py`) sees real
  identifier values, to block them.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.contracts import AskUserReply, AskUserRequest, CallJob, CallReport, Event
from app.contracts.common import (
    BriefId,
    CallId,
    CallState,
    CaseId,
    JobId,
    TranscriptId,
    UserId,
)
from app.phone.line import LineEvent


class LineClosed(Exception):
    """The line is gone (we or the agency hung up), so the action wasn't sent."""


class Telephony(Protocol):
    """One call's phone line. The methods are what we do; `events()` is what
    happens, including the results of `dial_agency` and `ring_user`."""

    async def dial_agency(self, call_id: CallId, case_id: CaseId) -> str:
        """Dial the case's verified official number; returns the Twilio call SID.
        Raises `UnverifiedNumber`: never fall back to another number. Whether the
        agency picks up arrives later as an event."""
        ...

    async def say(self, text: str) -> None:
        """Speak on the agency leg: menu choices (C37), the intro to the rep."""
        ...

    async def press_keys(self, digits: str) -> None:
        """Keypad fallback for a menu step that won't take speech (C37): 0-9, *, #."""
        ...

    async def ring_user(self, call_id: CallId, user_id: UserId) -> None:
        """Ring the user's own number (C6, C29) into the call's conference. Returns
        once it's ringing; `UserAnswered` or `UserUnreachable` follows. The agency
        leg stays on our line meanwhile, so the agent can keep the rep talking."""
        ...

    async def connect_user(self) -> None:
        """Move the agency leg into the conference, after `UserAnswered`."""
        ...

    async def hang_up(self) -> None:
        """End every leg. Safe to call more than once."""
        ...

    def events(self) -> AsyncIterator[LineEvent]:
        """Everything that happens on the line, in order. Ends after `hang_up`."""
        ...


class NumberSource(Protocol):
    """Where `Telephony` adapters get numbers. Deliberately not in `CallDeps`."""

    async def official_dial_number(self, case_id: CaseId) -> str:
        """Raises `UnverifiedNumber` unless the case is verified (rule 2)."""
        ...

    async def user_number(self, user_id: UserId) -> str:
        """Raises `NotFound` for an unknown user."""
        ...


class Relay(Protocol):
    async def ask_user(self, request: AskUserRequest) -> AskUserReply:
        """P1 as `app.relay.ask_user` implements it. On a timeout or a failed send the
        reply carries `default_option`. The relay writes `questions` and logs every
        `call.ask_user*` event, so the phone agent logs none of them.

        Don't await it inline: menus reprompt and hang up long before `timeout_s`.
        Run it as a task and keep reading `Telephony.events()`."""
        ...


class CaseReader(Protocol):
    async def get_brief(self, brief_id: BriefId) -> dict[str, Any]:
        """The case brief (`CaseBrief` is still a dict). Raises `NotFound`."""
        ...


class TranscriptLine(BaseModel):
    """One line of `transcripts.lines` (`writes.phone.save_transcript`)."""

    model_config = ConfigDict(frozen=True)

    at: datetime
    speaker: Literal["agent", "agency", "user"]
    text: str


class CallStore(Protocol):
    """The `calls` and `transcripts` tables, which only the phone agent writes."""

    async def create_call(self, job_id: JobId, job: CallJob) -> CallId:
        """Mint the call (C7). Consent comes from the job, so it can't be left out."""
        ...

    async def set_state(
        self, call_id: CallId, state: CallState, twilio_call_sid: str | None = None
    ) -> None: ...

    async def save_transcript(
        self, call_id: CallId, lines: Sequence[TranscriptLine]
    ) -> TranscriptId:
        """Create or replace the whole transcript; fine to call as the call goes on."""
        ...

    async def save_report(self, call_id: CallId, report: CallReport) -> None: ...


class EventLog(Protocol):
    async def append(self, event: Event) -> None: ...


class Clock(Protocol):
    """All waiting goes through here, never `asyncio.sleep` or `asyncio.timeout`,
    so tests and the simulator can run a 60-minute hold instantly."""

    def now(self) -> datetime:
        """Timezone-aware UTC."""
        ...

    async def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class CallDeps:
    """Everything one call runner needs from outside. One per call, because a
    `Telephony` is one call's line."""

    telephony: Telephony
    relay: Relay
    cases: CaseReader
    calls: CallStore
    events: EventLog
    clock: Clock
