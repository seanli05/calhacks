"""The real `Telephony`: one call's agency leg over Twilio (Phase 2), and the
applicant's leg bridged into it (Phase 3).

Three things feed one call's line, all in this one process:

- `dial_agency`, `press_keys`, `ring_user`, `connect_user`, and `hang_up` go out
  over the REST API (`CallControl`);
- Twilio's callbacks come back through `routes.py`: the agency leg's status
  (`on_status`), and the applicant leg's status and its join gate
  (`on_user_status`, `user_pressed_key`, `user_missed_gate`);
- the media stream's websocket (`routes.py` → `audio_pipeline.py`) attaches an
  `AudioStream` and emits speech events through `emit`. After the bridge, each
  leg's listen-only fork emits `Overheard` lines the same way;
- the listen leg, when the user sits in before the bridge (`listen_leg.py`): its
  callbacks and its stream (`listen_audio.py`) come through here to its `ListenLeg`.

The bridge (spikes/bridge/README.md): `ring_user` calls the applicant with a join
gate, because carrier voicemail picks up unanswered calls and Twilio reports that
as answered. A key press puts the applicant in the call's conference and emits
`UserAnswered`; `connect_user` then moves the agency leg in too. That ends the
agency leg's media stream, which from then on is expected, not a hang-up, and the
agent can't speak any more (rule 3).

With `join_gate=False` (`PHONE_JOIN_GATE=false`, for the demo) there's no gate: the
leg's TwiML is the conference itself, so picking up joins at once, and the first
sign of it (the `in-progress` callback or the leg's fork) emits `UserAnswered`.
Voicemail that picks up then joins too; the risk is accepted for the demo phone.

`LINES` maps each `call_id` to its line so the routes can find it. Twilio doesn't
promise the order of callbacks and streams, so the line keeps how far the agency
leg has got and never moves back: answered once (by the stream or the callback,
whichever comes first), gone once. A stream is numbered when it attaches, and a
close only counts for the current one, since `press_keys` swaps streams (C37).

Rules: no method takes a number. `dial_agency` reads the verified one from its
`NumberSource` (rule 2, with C40's demo swap inside `official_dial_number`), and
`UnverifiedNumber` propagates. `GuardedTelephony` wraps this (C35). No audio is
kept (C29), and logs carry IDs and statuses, never numbers or what was said.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from aiohttp import ClientError
from twilio.base.exceptions import TwilioRestException

from app.contracts.common import CallId, CaseId, LanguageCode, UserId
from app.phone.call_lines import JOIN_PROMPTS, join_prompt
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    AgencyUnreachable,
    HangUpRequested,
    LineEvent,
    UserAnswered,
    UserLeft,
    UserUnreachable,
)
from app.phone.listen_audio import ListenMixer, ListenSink
from app.phone.listen_leg import ListenInResult, ListenLeg
from app.phone.ports import LineClosed, NumberSource
from app.phone.twilio_rest import (
    ENDED_STATUSES,
    USER_RING_TIMEOUT_S,
    conference_twiml,
    hang_up_twiml,
    stream_twiml,
    user_gate_twiml,
)
from app.phone.twilio_urls import LineUrls, Speaker

logger = logging.getLogger(__name__)

type HangUpResult = Literal["ending", "call_over"]
"""What a request to end the call got: the runner is ending it, or it's over."""

type UserStage = Literal["none", "ringing", "joined", "gone"]
"""The applicant's leg: not rung yet, rung (and maybe picked up, by them or by
voicemail), joined by a key press, over."""

_UNREACHABLE = {"busy": "busy", "no-answer": "no_answer", "failed": "failed"}
_REST_ERRORS = (TwilioRestException, ClientError, TimeoutError)


class CallControl(Protocol):
    """Twilio's REST API for one account (`twilio_rest.TwilioCalls`)."""

    async def create(
        self, *, to: str, twiml: str, status_callback: str, ring_s: int = ...
    ) -> str: ...
    async def update_twiml(self, sid: str, twiml: str) -> None: ...
    async def complete(self, sid: str) -> None: ...
    async def end(self, sid: str) -> None: ...
    async def status(self, sid: str) -> str: ...


class AudioStream(Protocol):
    """One media stream's pipeline, as the line sees it (`audio_pipeline.py`)."""

    async def speak(self, text: str) -> None:
        """Returns once Twilio has played it. Raises `LineClosed` if the stream ends."""
        ...

    async def interrupt(self) -> None:
        """Stop speaking and drop audio Twilio hasn't played yet."""
        ...

    async def close(self) -> None:
        """End the pipeline. Never hangs up the call."""
        ...


@dataclass(frozen=True)
class LineTiming:
    stream_wait_s: float = 8.0
    """For the new stream after `press_keys` (about 2 s on a live line)."""
    gone_grace_s: float = 5.0
    """After a stream closes unasked, for Twilio's `completed` callback."""
    say_margin_s: float = 5.0
    """Added to the spoken length when waiting for a `say` to play."""
    hang_up_s: float = 10.0


class LineRegistry:
    """The live lines by `call_id`. One process, so a dict is enough."""

    def __init__(self) -> None:
        self._lines: dict[CallId, TwilioTelephony] = {}

    def add(self, call_id: CallId, line: "TwilioTelephony") -> None:
        if call_id in self._lines:
            raise RuntimeError(f"call {call_id} already has a line")
        self._lines[call_id] = line

    def get(self, call_id: CallId) -> "TwilioTelephony | None":
        return self._lines.get(call_id)

    def remove(self, call_id: CallId, line: "TwilioTelephony") -> None:
        if self._lines.get(call_id) is line:
            del self._lines[call_id]


LINES = LineRegistry()


def say_seconds(text: str) -> float:
    """About how long `text` takes to say (2.5 words per second)."""
    return len(text.split()) / 2.5


class TwilioTelephony:
    """One call's agency leg, and the applicant's leg bridged into it.
    `user_language` is the call job's: the join gate speaks it. Without
    `join_gate`, the applicant joins as soon as their phone picks up."""

    def __init__(
        self,
        numbers: NumberSource,
        calls: CallControl,
        urls: LineUrls,
        *,
        user_language: LanguageCode,
        registry: LineRegistry = LINES,
        timing: LineTiming | None = None,
        join_gate: bool = True,
    ) -> None:
        self._numbers = numbers
        self._calls = calls
        self._urls = urls
        self._user_language = user_language
        self._registry = registry
        self._timing = timing or LineTiming()
        self._join_gate = join_gate
        self._queue: asyncio.Queue[LineEvent | None] = asyncio.Queue()
        self._call_id: CallId | None = None
        self._sid: str | None = None
        self._answered = False
        self._agency_gone = False
        self._hung_up = False
        self._stream: AudioStream | None = None
        self._stream_seq = 0
        self._stream_changed = asyncio.Event()
        self._reconnecting = False
        self._keys_lock = asyncio.Lock()
        self._gone_check: asyncio.Task[None] | None = None
        self._user_sid: str | None = None
        self._old_user_sids: set[str] = set()
        """Legs from earlier rings: their callbacks are stale."""
        self._user_stage: UserStage = "none"
        self._bridged = False
        """The agency leg was moved into the conference."""
        self._listen = ListenLeg(calls, urls, self.emit, language=user_language)

    def __repr__(self) -> str:
        return f"TwilioTelephony(call_id={self._call_id})"

    # Telephony

    async def dial_agency(self, call_id: CallId, case_id: CaseId) -> str:
        if self._call_id is not None:
            raise RuntimeError("this line already dialed")
        number = await self._numbers.official_dial_number(case_id)
        self._call_id = call_id
        self._registry.add(call_id, self)
        try:
            sid = await self._calls.create(
                to=number,
                twiml=stream_twiml(self._urls.stream(call_id)),
                status_callback=self._urls.status(call_id),
            )
        except BaseException:
            self._registry.remove(call_id, self)
            raise
        # A callback may already have told us the SID; the REST answer is the truth.
        self._sid = sid
        logger.info("dialed the agency (call_id=%s sid=%s)", call_id, sid)
        return sid

    async def say(self, text: str) -> None:
        stream = await self._live_stream()
        wait = say_seconds(text) + self._timing.say_margin_s
        try:
            async with asyncio.timeout(wait):
                await stream.speak(text)
        except TimeoutError:
            # Twilio never confirmed playback; carry on rather than stall the call.
            logger.warning(
                "no playback mark after %.0f s (call_id=%s)", wait, self._call_id
            )
        except asyncio.CancelledError:
            await stream.interrupt()
            raise

    async def press_keys(self, digits: str) -> None:
        """C37's keypad fallback: `<Play digits>`, then a new stream. Returns once the
        new stream is up; if it never comes, the line is given up (`LineClosed`)."""
        self._require_agency()
        async with self._keys_lock:
            self._require_agency()
            before = self._stream_seq
            self._reconnecting = True
            try:
                await self._calls.update_twiml(
                    self._require_sid(),
                    stream_twiml(
                        self._urls.stream(self._require_call_id()),
                        play_digits="w" + digits,
                    ),
                )
                async with asyncio.timeout(self._timing.stream_wait_s):
                    await self._wait_for_stream(after=before)
            except _REST_ERRORS as exc:
                logger.warning(
                    "keys didn't go through (call_id=%s): %s",
                    self._call_id,
                    type(exc).__name__,
                )
                await self._give_up_line()
                raise LineClosed("the line didn't come back after the keys") from exc
            finally:
                self._reconnecting = False

    async def ring_user(self, call_id: CallId, user_id: UserId) -> None:
        """A failed REST call doesn't raise: it's `UserUnreachable("failed")`, so the
        representative still hears that the account holder will call back. If the
        user is listening in, their leg joins the conference instead of a ring.
        Called again after a missed ring, it rings a new leg: the earlier one is
        ended if it's still ringing, and its callbacks no longer count."""
        self._require_agency()
        if call_id != self._call_id:
            raise RuntimeError("ring_user for another call")
        if self._user_stage == "joined":
            raise RuntimeError("the applicant has already joined")
        if self._user_stage != "none":
            await self._forget_user_leg()
        self._listen.drop_request()
        if await self._promote_listener(call_id):
            return
        if (sid := self._listen.live_sid()) is not None:
            # Still at the listen gate: end it, and ring for the bridge instead.
            self._listen.end("failed")
            await self._end_leg("listener", self._calls.end, sid)
        number = await self._numbers.user_number(user_id)
        if self._join_gate and self._user_language not in JOIN_PROMPTS:
            logger.warning(
                "no join prompt in %r; using English (call_id=%s)",
                self._user_language,
                call_id,
            )
        self._user_stage = "ringing"
        try:
            sid = await self._calls.create(
                to=number,
                twiml=self._user_twiml(call_id),
                status_callback=self._urls.user_status(call_id),
                ring_s=USER_RING_TIMEOUT_S,
            )
        except _REST_ERRORS as exc:
            logger.warning(
                "ringing the applicant failed (call_id=%s): %s",
                call_id,
                type(exc).__name__,
            )
            self._user_gone(UserUnreachable(reason="failed"))
            return
        self._user_sid = self._user_sid or sid
        logger.info("rang the applicant (call_id=%s sid=%s)", call_id, sid)

    async def listen_in(self, call_id: CallId, user_id: UserId) -> None:
        """Ring the user's own number (C6) on a listen-only leg, after
        `request_listen_in`. A failed ring is `ListenEnded("failed")`; an unknown user
        ends the request too, then raises."""
        try:
            self._require_agency()
        except LineClosed:
            self._listen.drop_request()
            raise
        if call_id != self._call_id:
            raise RuntimeError("listen_in for another call")
        if self._user_stage != "none":
            self._listen.drop_request()  # a person picked up first; the bridge rings
            return
        try:
            number = await self._numbers.user_number(user_id)
        except Exception:
            self._listen.end("failed")
            raise
        await self._listen.ring(call_id, number)

    async def connect_user(self) -> None:
        self._require_agency()
        if self._user_stage != "joined":
            raise RuntimeError("the applicant hasn't joined")
        # Before the update: it ends the stream, and that close isn't a hang-up.
        self._bridged = True
        call_id = self._require_call_id()
        try:
            await self._calls.update_twiml(
                self._require_sid(),
                conference_twiml(
                    self._conference(), self._urls.fork(call_id, "agency")
                ),
            )
        except _REST_ERRORS as exc:
            self._bridged = False
            logger.warning(
                "moving the agency leg failed (call_id=%s): %s",
                call_id,
                type(exc).__name__,
            )
            await self._give_up_line()
            raise LineClosed("the agency leg couldn't join the applicant") from exc
        logger.info("bridged (call_id=%s)", call_id)

    async def hang_up(self) -> None:
        if self._hung_up:
            return
        self._hung_up = True
        if self._call_id is not None:
            self._registry.remove(self._call_id, self)
        if self._gone_check is not None:
            self._gone_check.cancel()
        if self._sid is not None and not self._agency_gone:
            await self._end_leg("agency", self._calls.complete, self._sid)
        if self._user_sid is not None and self._user_stage in ("ringing", "joined"):
            # Twilio refuses `completed` for a call still ringing; `end` cancels it.
            await self._end_leg("applicant", self._calls.end, self._user_sid)
        if (listen_sid := self._listen.live_sid()) is not None:
            self._listen.end("hung_up")
            await self._end_leg("listener", self._calls.end, listen_sid)
        stream, self._stream = self._stream, None
        self._wake()
        if stream is not None:
            await stream.close()
        self._queue.put_nowait(None)

    async def events(self) -> AsyncIterator[LineEvent]:
        while (event := await self._queue.get()) is not None:
            yield event

    # Listening in

    def request_listen_in(self) -> ListenInResult:
        """The user asked to sit in. Rings them through the runner (`ListenRequested`
        → `listen_in`), since only the runner knows whose call this is."""
        if self._call_id is None or self._hung_up or self._agency_gone:
            return "call_over"
        if self._user_stage != "none" or self._bridged:
            return "rep_on_line"
        return self._listen.request()

    def request_hang_up(self) -> HangUpResult:
        """The user asked to end the call. The runner ends it (`HangUpRequested`), so
        the report is written and a waiting representative hears goodbye first."""
        if self._call_id is None or self._hung_up or self._agency_gone:
            return "call_over"
        self.emit(HangUpRequested())
        return "ending"

    @property
    def listen_mixer(self) -> ListenMixer:
        """For the agency stream's taps (`audio_pipeline.run_stream`)."""
        return self._listen.mixer

    def on_listen_status(self, call_sid: str, status: str) -> None:
        """A status callback for the listen leg; once it joined the bridge, for the
        applicant's leg."""
        if self._user_sid is not None and call_sid == self._user_sid:
            self.on_user_status(call_sid, status)
            return
        logger.info("listen leg %s (call_id=%s)", status, self._call_id)
        self._listen.on_status(call_sid, status)

    def listen_pressed_key(self, call_sid: str) -> str:
        if self._hung_up or self._agency_gone or self._call_id is None:
            return hang_up_twiml()
        return self._listen.pressed_key(call_sid, self._call_id)

    def listen_missed_gate(self, call_sid: str) -> str:
        return self._listen.missed_gate(call_sid)

    def attach_listener(self, sink: ListenSink, call_sid: str) -> bool:
        return not self._hung_up and self._listen.attach(sink, call_sid)

    def detach_listener(self, sink: ListenSink) -> None:
        self._listen.detach(sink)

    # From the routes and the stream

    def on_status(self, call_sid: str, status: str) -> None:
        """A Twilio status callback for this call."""
        if not self._matches(call_sid):
            logger.warning(
                "status for another call's SID ignored (call_id=%s)", self._call_id
            )
            return
        self._sid = self._sid or call_sid
        logger.info("agency leg %s (call_id=%s)", status, self._call_id)
        if status == "in-progress":
            self._answer()
        elif status in _UNREACHABLE or status == "canceled":
            if self._answered:
                self._agency_ended()
            else:
                self._gone(AgencyUnreachable(reason=_UNREACHABLE.get(status, "failed")))
        elif status == "completed":
            self._agency_ended()

    def on_user_status(self, call_sid: str, status: str) -> None:
        """A Twilio status callback for the applicant's leg."""
        if not self._matches_user(call_sid):
            logger.warning(
                "applicant status for another SID ignored (call_id=%s)", self._call_id
            )
            return
        self._user_sid = self._user_sid or call_sid
        logger.info("applicant leg %s (call_id=%s)", status, self._call_id)
        if self._user_stage == "ringing":
            if status == "in-progress" and not self._join_gate:
                self._user_picked_up(call_sid)
            elif status in _UNREACHABLE or status == "canceled":
                self._user_gone(
                    UserUnreachable(reason=_UNREACHABLE.get(status, "failed"))
                )
            elif status == "completed":
                # Picked up, then put down before pressing a key.
                self._user_gone(UserUnreachable(reason="no_key_press"))
        elif self._user_stage == "joined" and status in ENDED_STATUSES:
            self._user_gone(UserLeft())

    def user_pressed_key(self, call_sid: str) -> str:
        """The applicant pressed a key at the join gate: TwiML for their leg, which
        joins them to the conference, or hangs up if the call can't take them any
        more (the agency left, the runner gave up on them, or we hung up)."""
        if (
            not self._matches_user(call_sid)
            or self._user_stage != "ringing"
            or self._hung_up
            or self._agency_gone
        ):
            logger.info(
                "key press too late (call_id=%s stage=%s)",
                self._call_id,
                self._user_stage,
            )
            return hang_up_twiml()
        self._user_joined(call_sid)
        return conference_twiml(
            self._conference(), self._urls.fork(self._require_call_id(), "user")
        )

    def _user_picked_up(self, call_sid: str) -> None:
        """No gate: the applicant's leg answered, so they're in the conference.
        Called by whichever comes first, the callback or the fork."""
        if (
            self._join_gate
            or not self._matches_user(call_sid)
            or self._user_stage != "ringing"
            or self._hung_up
            or self._agency_gone
        ):
            return
        self._user_joined(call_sid)

    def _user_joined(self, call_sid: str) -> None:
        self._user_sid = self._user_sid or call_sid
        self._user_stage = "joined"
        self.emit(UserAnswered())

    def _user_twiml(self, call_id: CallId) -> str:
        """What the applicant's leg runs on pick-up: the join gate, or with no gate
        the conference itself."""
        if not self._join_gate:
            return conference_twiml(
                self._conference(), self._urls.fork(call_id, "user")
            )
        return user_gate_twiml(
            join_prompt(self._user_language),
            self._urls.user_joined(call_id),
            self._urls.user_missed(call_id),
        )

    def user_missed_gate(self, call_sid: str) -> str:
        """No key after the join prompt: voicemail, or a phone put down."""
        if self._matches_user(call_sid) and self._user_stage == "ringing":
            self._user_gone(UserUnreachable(reason="no_key_press"))
        return hang_up_twiml()

    def attach_fork(self, speaker: Speaker, call_sid: str) -> bool:
        """A listen-only fork connected. Only a joined leg's own SID may fork it."""
        if self._hung_up:
            return False
        if speaker == "agency":
            return self._bridged and call_sid == self._sid
        self._user_picked_up(call_sid)
        return self._user_stage == "joined" and call_sid == self._user_sid

    def attach_stream(self, stream: AudioStream, call_sid: str) -> int | None:
        """A media stream connected. Returns its number, or None if the line won't
        take it (ours hung up, the agency leg is bridged, or the SID doesn't
        match): close it then."""
        if (
            self._hung_up
            or self._agency_gone
            or self._bridged
            or not self._matches(call_sid)
        ):
            return None
        self._sid = self._sid or call_sid
        self._stream_seq += 1
        self._stream = stream
        self._wake()
        self._answer()
        logger.info("stream %d up (call_id=%s)", self._stream_seq, self._call_id)
        return self._stream_seq

    def detach_stream(self, seq: int) -> None:
        if seq != self._stream_seq or self._stream is None:
            return  # an older stream, already replaced
        self._stream = None
        logger.info("stream %d down (call_id=%s)", seq, self._call_id)
        if not (
            self._reconnecting or self._hung_up or self._agency_gone or self._bridged
        ):
            # A <Connect><Stream> that ends ends the call; `completed` should follow.
            self._gone_check = asyncio.create_task(self._end_if_still_gone())

    def emit(self, event: LineEvent) -> None:
        if not self._hung_up:
            self._queue.put_nowait(event)

    # Inside

    def _answer(self) -> None:
        if not self._answered and not self._agency_gone:
            self._answered = True
            self.emit(AgencyAnswered())

    def _agency_ended(self) -> None:
        self._gone(AgencyHungUp())

    def _gone(self, event: LineEvent) -> None:
        if self._agency_gone or self._hung_up:
            return
        self._agency_gone = True
        self.emit(event)
        self._wake()

    def _wake(self) -> None:
        """Wake whoever waits for a stream: one came, or the line is over."""
        self._stream_changed.set()
        self._stream_changed = asyncio.Event()

    def _user_gone(self, event: LineEvent) -> None:
        if self._user_stage == "gone":
            return
        self._user_stage = "gone"
        self.emit(event)

    def _matches(self, call_sid: str) -> bool:
        return self._sid is None or call_sid == self._sid

    def _matches_user(self, call_sid: str) -> bool:
        if self._user_stage == "none" or call_sid in self._old_user_sids:
            return False
        return self._user_sid is None or call_sid == self._user_sid

    async def _promote_listener(self, call_id: CallId) -> bool:
        """Move a listening user's leg into the conference: they join with no second
        ring and no gate (they pressed a key to listen). False if nobody listens, or
        the move failed, in which case their leg is ended and the bridge rings."""
        sid = self._listen.take_for_bridge()
        if sid is None:
            return False
        try:
            await self._calls.update_twiml(
                sid,
                conference_twiml(self._conference(), self._urls.fork(call_id, "user")),
            )
        except _REST_ERRORS as exc:
            logger.warning(
                "moving the listener to the bridge failed (call_id=%s): %s",
                call_id,
                type(exc).__name__,
            )
            await self._end_leg("listener", self._calls.end, sid)
            return False
        self._user_sid = sid
        self._user_stage = "joined"
        self.emit(UserAnswered())
        logger.info("listener joined the bridge (call_id=%s sid=%s)", call_id, sid)
        return True

    def _conference(self) -> str:
        return f"bridge-{self._require_call_id()}"

    async def _forget_user_leg(self) -> None:
        """Before ringing again: end the earlier leg if it may still ring (the
        runner's backstop gave up on it), and ignore its callbacks from now on."""
        old_sid, stage = self._user_sid, self._user_stage
        self._user_sid = None
        self._user_stage = "none"
        if old_sid is None:
            return
        self._old_user_sids.add(old_sid)
        if stage == "ringing":
            await self._end_leg("applicant", self._calls.end, old_sid)

    async def _end_leg(
        self, leg: str, end: Callable[[str], Awaitable[None]], sid: str
    ) -> None:
        try:
            async with asyncio.timeout(self._timing.hang_up_s):
                await end(sid)
        except _REST_ERRORS as exc:
            logger.warning(
                "ending the %s leg failed (call_id=%s): %s",
                leg,
                self._call_id,
                type(exc).__name__,
            )

    def _require_agency(self) -> None:
        if self._call_id is None:
            raise RuntimeError("dial the agency first")
        if self._hung_up or self._agency_gone:
            raise LineClosed("the agency leg has ended")
        if self._bridged:
            raise LineClosed("the applicant is on the call; the agent is silent")

    def _require_sid(self) -> str:
        if self._sid is None:
            raise LineClosed("the call was never placed")
        return self._sid

    def _require_call_id(self) -> CallId:
        if self._call_id is None:
            raise RuntimeError("dial the agency first")
        return self._call_id

    async def _live_stream(self) -> AudioStream:
        self._require_agency()
        if self._stream is None:
            try:
                async with asyncio.timeout(self._timing.stream_wait_s):
                    await self._wait_for_stream(after=self._stream_seq - 1)
            except TimeoutError as exc:
                raise LineClosed("no media stream to speak on") from exc
        self._require_agency()
        if self._stream is None:
            raise LineClosed("no media stream to speak on")
        return self._stream

    async def _wait_for_stream(self, *, after: int) -> None:
        while self._stream_seq <= after or self._stream is None:
            self._require_agency()
            await self._stream_changed.wait()

    async def _give_up_line(self) -> None:
        """After `press_keys` failed: the agency hung up, or we hang up."""
        try:
            status = await self._calls.status(self._require_sid())
        except _REST_ERRORS:
            status = "unknown"
        if status in ENDED_STATUSES:
            self._agency_ended()
        else:
            await self.hang_up()

    async def _end_if_still_gone(self) -> None:
        await asyncio.sleep(self._timing.gone_grace_s)
        if self._stream is None and not self._reconnecting:
            logger.warning("stream ended with no callback (call_id=%s)", self._call_id)
            self._agency_ended()
