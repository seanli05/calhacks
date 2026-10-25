"""Call runner (1e): one call end to end on `CallDeps` (Plan.md → Phone agent).

One inbox, one handler at a time. The pump (line events), the ask_user task, and
the timers only post inputs; the main loop handles them in order, so the runner's
own state needs no locks. Claude calls (1b, 1c) are awaited inside a handler, and
whatever arrives meanwhile waits in the inbox, stamped with when it arrived.

Wrap-up is a `finally`, not a step: however the drive loop exits (hang-up, timeout,
crash), the call reaches `ended` through `wrap_up` with a saved report, and the
line is always hung up. Conventions and the reasons behind each policy are in
docs/specs/phone-ports.md → The runner.

Split by job: `runner_parts.py` (config, inbox inputs, timers), `runner_base.py`
(shared state and primitives), `runner_menu.py` (menu and ask_user handlers), and
this file (the call's lifecycle, dispatch, hold, the person, the bridge).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from app.contracts import CallJob, CallReport, EventType
from app.contracts.common import CallState, JobId
from app.phone import call_lines, phase
from app.phone.clock import with_timeout
from app.phone.guard import GuardedTelephony
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    AgencyUnreachable,
    HangUpRequested,
    Heard,
    ListenEnded,
    ListenRequested,
    ListenStarted,
    NonSpeech,
    Overheard,
    SpeechStarted,
    UserAnswered,
    UserLeft,
    UserUnreachable,
)
from app.phone.llm import LlmClient
from app.phone.observe import Observer
from app.phone.phase import PhaseReading
from app.phone.ports import CallDeps, LineClosed
from app.phone.report import ReportBuilder, ReportInput, build_report
from app.phone.runner_menu import MenuSteps
from app.phone.runner_parts import (
    AskDone,
    Input,
    LineEnded,
    LineInput,
    MenuGaveUp,
    RunnerConfig,
    TimerFired,
)
from app.phone.state import TRANSITIONS, Transition, Trigger

logger = logging.getLogger(__name__)

S = CallState

__all__ = ["MenuGaveUp", "RunnerConfig", "run_call"]


async def run_call(
    job_id: JobId,
    job: CallJob,
    deps: CallDeps,
    *,
    llm: LlmClient | None = None,
    observer: Observer | None = None,
    config: RunnerConfig | None = None,
    report_builder: ReportBuilder = build_report,
) -> CallReport:
    """Run one call and return its saved report. Raises only if the call couldn't be
    created or the report couldn't be saved; every other failure ends in a report.

    `deps.telephony` must be a `GuardedTelephony` (C35). `llm` defaults to Claude."""
    if not isinstance(deps.telephony, GuardedTelephony):
        raise TypeError("the runner needs a GuardedTelephony (C35)")
    runner = _CallRunner(
        job_id, job, deps, llm, observer, config or RunnerConfig(), report_builder
    )
    return await runner.run()


_SUMMARIES = {
    EventType.CALL_ON_HOLD: "On hold",
    EventType.CALL_HUMAN_DETECTED: "A person picked up",
    EventType.CALL_USER_DIALED: "Calling the applicant to join",
    EventType.CALL_USER_JOINED: "The applicant joined the call",
    EventType.CALL_USER_UNREACHABLE: (
        "The applicant didn't answer; the representative was told they'll call back"
    ),
    EventType.CALL_ENDED: "Call ended",
}
_ABORTABLE = frozenset(
    state for (state, trigger) in TRANSITIONS if trigger == Trigger.AGENT_ABORTED
)
_DRIVING = frozenset(set(CallState) - {S.WRAP_UP, S.ENDED})


class _CallRunner(MenuSteps):
    """One call: its lifecycle, line-event dispatch, hold, the person, the bridge."""

    async def run(self) -> CallReport:
        self.call_id = await self.deps.calls.create_call(self.job_id, self.job)
        self.events = self.events.for_call(self.call_id)
        try:
            await self._drive()
            return await self._wrap_up()
        except asyncio.CancelledError:
            try:
                await with_timeout(
                    self.clock, self._finish_cancelled(), self.config.cleanup_timeout_s
                )
            except Exception:
                logger.exception("wrap-up after cancel failed (%s)", self._ids())
            raise
        finally:
            await self._hang_up()
            await self._stop_tasks()

    async def _drive(self) -> None:
        try:
            await self._dial()
            await self._loop()
        except MenuGaveUp as exc:
            logger.warning("call gave up (%s): %s", self._ids(), exc)
            await self._crashed(exc)
        except Exception as exc:
            logger.exception("call runner failed (%s)", self._ids())
            await self._crashed(exc)

    async def _crashed(self, exc: Exception) -> None:
        self.error = type(exc).__name__
        self._begin("error", text=self.error)
        self.step.flags.append(f"error:{self.error}")
        if self.sm.state == S.CONNECTED:
            # The applicant and the rep are talking: keep the bridge up and only
            # watch for the end (there's no abort from `connected`).
            self.passive = True
            self._emit()
            try:
                await self._loop()
            except Exception:
                logger.exception("passive watch failed (%s)", self._ids())
                if self.sm.state == S.CONNECTED:
                    self._begin("error", text="passive watch failed")
                    try:
                        await self._fire(Trigger.CALL_FINISHED)
                    finally:
                        self._emit()
            return
        try:
            if self.sm.state in _ABORTABLE:
                await self._fire(Trigger.AGENT_ABORTED)
        finally:
            self._emit()

    async def _finish_cancelled(self) -> None:
        """Best effort when the runner itself is cancelled: a failed report."""
        self.error = self.error or "CancelledError"
        if self.sm.state in _ABORTABLE:
            await self._fire(Trigger.AGENT_ABORTED)
        elif self.sm.state == S.CONNECTED:
            await self._fire(Trigger.CALL_FINISHED)
        if self.sm.state == S.WRAP_UP:
            await self._wrap_up()

    async def _dial(self) -> None:
        self._begin("dial")
        try:
            self.brief = await self.deps.cases.get_brief(self.job.brief_id)
            sid = await self.deps.telephony.dial_agency(self.call_id, self.job.case_id)
            await self.deps.calls.set_state(self.call_id, S.DIALING, sid)
            # Logged only once the dial went out: it tells the user "Calling now".
            await self._log(EventType.CALL_DIALING, "Calling the agency")
            self.step.sent.append("dialed the verified number")
            self.pump = asyncio.create_task(self._pump())
        finally:
            self._emit()

    async def _loop(self) -> None:
        while self.sm.state in _DRIVING:
            item = await self.inbox.get()
            self._begin_for(item)
            try:
                await self._handle(item)
            finally:
                self._emit()

    async def _wrap_up(self) -> CallReport:
        self._begin("wrap_up")
        try:
            self._stop_background()
            await self._hang_up()
            await self._settle_live_save(cancel=False)
            transcript_id = await self._retry_once(
                lambda: self.deps.calls.save_transcript(self.call_id, self.transcript)
            )
            cause = next(
                (
                    t.trigger
                    for t in reversed(self.sm.history)
                    if t.to_state == S.WRAP_UP
                ),
                None,
            )
            report = await self.report_builder(
                ReportInput(
                    call_id=self.call_id,
                    case_id=self.job.case_id,
                    outcome=self.sm.outcome,
                    cause=cause,
                    transcript_id=transcript_id,
                    transcript=tuple(self.transcript),
                    brief=self.brief,
                )
            )
            await self._retry_once(
                lambda: self.deps.calls.save_report(self.call_id, report)
            )
            minutes = round((self.clock.now() - self.started) / timedelta(minutes=1))
            ended = {"minutes": minutes, "outcome": report.outcome, "cause": cause}
            if self.error:
                ended["error"] = self.error
            await self._fire(Trigger.REPORT_SAVED, **ended)
            return report
        finally:
            self._emit()

    async def _pump(self) -> None:
        try:
            async for event in self.deps.telephony.events():
                seq = 0
                if isinstance(event, Heard):
                    self.heard_arrived += 1
                    seq = self.heard_arrived
                self.inbox.put_nowait(LineInput(event, self.now_s(), seq))
        except Exception:
            logger.exception("line event stream failed (%s)", self._ids())
        self.inbox.put_nowait(LineEnded(self.now_s()))

    def _stop_background(self) -> None:
        self.timers.cancel_all()
        if self.ask is not None:
            self._drop_ask()
        if self.speaking is not None:
            self.speaking.cancel()
            self._dropped.append(self.speaking)
            self.speaking = None

    async def _stop_tasks(self) -> None:
        self._stop_background()
        await self._settle_live_save(cancel=True)
        tasks = [*self._dropped, *([self.pump] if self.pump else [])]
        for task in tasks:
            task.cancel()
        # Let cancelled tasks (the relay's ask among them) finish cleaning up.
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _hang_up(self) -> None:
        try:
            await with_timeout(
                self.clock, self.deps.telephony.hang_up(), self.config.cleanup_timeout_s
            )
        except Exception:
            logger.exception(
                "hang_up failed; the line may still be up (%s)", self._ids()
            )

    async def _handle(self, item: Input) -> None:
        match item:
            case LineInput():
                await self._line_event(item)
            case LineEnded():
                await self._line_ended()
            case AskDone():
                await self._ask_done(item)
            case TimerFired():
                await self._timer(item)

    async def _line_event(self, item: LineInput) -> None:
        self._track_turn(item)
        await self._dispatch(item)
        if isinstance(item.event, Heard | NonSpeech):
            self.arm_held()

    def _track_turn(self, item: LineInput) -> None:
        match item.event:
            case SpeechStarted():
                self.line_speaking = True
                self.timers.start("turn_backstop", self.config.turn_backstop_s)
            case Heard():
                self._turn_closed(item.at_s)
            case NonSpeech() if self.line_speaking:
                self._turn_closed(item.at_s)

    def _turn_closed(self, at_s: float) -> None:
        self.line_speaking = False
        self.quiet_since_s = at_s
        self.timers.cancel("turn_backstop")

    async def _dispatch(self, item: LineInput) -> None:
        state = self.sm.state
        match item.event:
            case Overheard(speaker=speaker, text=text):
                # A fork can open a moment before `USER_JOINED`; keep its lines too.
                self._said(speaker, text)
            case SpeechStarted():
                self.speech_started()
            case Heard(text=text):
                self._said("agency", text)
                if self.passive:
                    return
                if state == S.DIALING:
                    # Speech before the answered callback: the line is answered.
                    self.step.flags.append("implied_answer")
                    await self._answered()
                    state = self.sm.state
                if state == S.MENU:
                    await self._menu_heard(text, item.at_s, item.heard_seq)
                elif state in (S.HOLD, S.HUMAN_DETECTED):
                    await self._listen(text, item.at_s, item.heard_seq)
                elif state == S.BRIDGING:
                    await self._bridging_heard(item.at_s)
            case NonSpeech(sound="music", seconds=seconds) if (
                state == S.MENU
                and seconds >= self.config.music_to_hold_s
                and not self.passive
            ):
                await self._fire(Trigger.HOLD_STARTED, cue="music")
            case AgencyAnswered() if state == S.DIALING and not self.passive:
                await self._answered()
            case AgencyUnreachable(reason=reason) if state == S.DIALING:
                await self._fire(Trigger.NO_ANSWER, reason=reason)
            case AgencyHungUp() if state == S.DIALING:
                await self._fire(Trigger.NO_ANSWER, reason="hung_up")
            case AgencyHungUp() if (state, Trigger.AGENCY_HUNG_UP) in TRANSITIONS:
                await self._fire(Trigger.AGENCY_HUNG_UP)
            case UserAnswered() if state == S.BRIDGING and not self.passive:
                await self._user_answered()
            case UserUnreachable(reason=reason) if state == S.BRIDGING:
                await self._user_unreachable(reason)
            case UserLeft() if state == S.CONNECTED:
                await self._fire(Trigger.CALL_FINISHED, cause="user_left")
            case HangUpRequested():
                await self._user_ended()
            case ListenRequested():
                await self._listen_in()
            case ListenStarted():
                self.listening_in = True
                self.step.sent.append("the user is listening in")
                logger.info("user listening in (%s)", self._ids())
            case ListenEnded(reason=reason):
                # Only their leg: the call with the agency goes on.
                self.listening_in = False
                self.step.flags.append(f"listen_ended:{reason}")
                logger.info("listen-in ended: %s (%s)", reason, self._ids())
            case NonSpeech():
                pass
            case _:
                self.step.flags.append("ignored")

    async def _line_ended(self) -> None:
        """The event stream ended without saying why: the agency leg is gone."""
        self.step.flags.append("line_ended")
        state = self.sm.state
        if state == S.DIALING:
            await self._fire(Trigger.NO_ANSWER, reason="line_ended")
        elif state == S.CONNECTED:
            await self._fire(Trigger.CALL_FINISHED, cause="line_ended")
        elif (state, Trigger.AGENCY_HUNG_UP) in TRANSITIONS:
            await self._fire(Trigger.AGENCY_HUNG_UP)

    async def _timer(self, fired: TimerFired) -> None:
        if not self.timers.take(fired):
            self.step.flags.append("stale_timer")
            return
        state = self.sm.state
        match fired.name:
            case "hold_limit" if state == S.HOLD:
                await self._fire(Trigger.HOLD_TIMEOUT)
            case "hold_limit":
                # Back in a menu, or with a person who may yet transfer us: time
                # out on the next hold.
                self.hold_overdue = True
                self.step.flags.append("hold_overdue")
            case "menu_budget" if state == S.MENU and not self.passive:
                raise MenuGaveUp("menu time budget used up")
            case "menu_quiet" if state == S.MENU and not self.passive:
                await self.send_held()
            case "turn_backstop":
                self.step.flags.append("turn_never_closed")
                self._turn_closed(fired.at_s)
                self.arm_held()
            case "user_backstop" if state == S.BRIDGING:
                await self._user_unreachable("no_answer")

    async def _answered(self) -> None:
        await self._fire(Trigger.AGENCY_ANSWERED)

    async def _listen(self, text: str, at_s: float, seq: int) -> None:
        reading = await self._classify(text, at_s)
        trigger = phase.to_trigger(self.sm.state, reading)
        if trigger is None:
            return
        await self._fire_reading(trigger, reading)
        if trigger == Trigger.MENU_RETURNED:
            # The utterance that showed the menu is its prompt: answer it now, or
            # the menu times out waiting.
            self.executor.observe(text)
            self.menu_buffer = [text]
            await self._classify_and_decide(at_s, seq, reading)

    async def _on_human(self) -> None:
        """Ring the applicant at once (< 5 s) and introduce the agent meanwhile. The
        intro plays in the background, so the applicant joining never waits on it.
        A user listening in is moved straight into the call instead, with no intro:
        they're already there to speak for themselves. Ringing takes the listen leg
        either way, so it no longer counts."""
        listening, self.listening_in = self.listening_in, False
        if listening:
            self.step.flags.append("listener_joins_without_intro")
        else:
            self._speak_meanwhile(call_lines.INTRO)
        await self._ring_user()

    async def _ring_user(self) -> None:
        """Ring the applicant, and log it (`call.user_dialed`, with the attempt)."""
        self.user_rings += 1
        try:
            await self.deps.telephony.ring_user(self.call_id, self.job.user_id)
        except LineClosed:
            self.step.flags.append("line_closed")
            return  # the hang-up event follows
        except BaseException:
            await self._stop_speaking()
            raise
        self.step.sent.append("rang the applicant")
        await self._fire(Trigger.USER_DIALED, attempt=self.user_rings)

    async def _bridging_heard(self, at_s: float) -> None:
        gap_ok = (
            self.last_holding_s is None
            or at_s - self.last_holding_s >= self.config.holding_line_gap_s
        )
        speaking = self.speaking is not None and not self.speaking.done()
        if speaking or self.holding_said >= self.config.holding_lines_max or not gap_ok:
            self.step.flags.append("quiet")
            return
        self.holding_said += 1
        self.last_holding_s = at_s
        self._speak_meanwhile(call_lines.HOLDING)

    async def _user_answered(self) -> None:
        await self._stop_speaking()
        try:
            await self.deps.telephony.connect_user()
        except LineClosed:
            self.step.flags.append("line_closed")
            return  # the hang-up event follows
        self.step.sent.append("connected the applicant")
        await self._fire(Trigger.USER_JOINED)

    async def _user_ended(self) -> None:
        """The user asked to end the call. A representative waiting for the applicant
        hears a fixed goodbye first; then wrap-up hangs up every leg."""
        state = self.sm.state
        if (state, Trigger.USER_ENDED) not in TRANSITIONS:
            self.step.flags.append("ignored")
            return
        if state in (S.HUMAN_DETECTED, S.BRIDGING):
            await self._stop_speaking()
            await self._say_line(call_lines.USER_ENDED)
        await self._fire(Trigger.USER_ENDED)

    async def _listen_in(self) -> None:
        """Ring the user to sit in. Listening runs beside the call's states, so a
        failure here is logged and the call goes on."""
        try:
            await self.deps.telephony.listen_in(self.call_id, self.job.user_id)
        except LineClosed:
            self.step.flags.append("line_closed")
            return
        except Exception:
            logger.exception("ringing the user to listen in failed (%s)", self._ids())
            self.step.flags.append("listen_failed")
            return
        self.step.sent.append("rang the user to listen in")

    async def _user_unreachable(self, reason: str) -> None:
        """A missed ring rings once more (`user_ring_attempts`) while the rep hears
        a fixed line; only the last miss gets the call-back line."""
        await self._stop_speaking()
        if self.user_rings < self.config.user_ring_attempts:
            self.step.flags.append(f"ring_again:{reason}")
            self.holding_said = 0
            self.last_holding_s = None
            self._speak_meanwhile(call_lines.RINGING_AGAIN)
            await self._ring_user()
            return
        await self._say_line(call_lines.CALL_BACK)
        await self._fire(Trigger.USER_UNREACHABLE, reason=reason)

    def _speak_meanwhile(self, text: str) -> None:
        """A fixed line to the rep while the applicant's phone rings, played in the
        background so the inbox keeps moving."""
        self.speaking = asyncio.ensure_future(self._say_in_background(text))

    async def _say_in_background(self, text: str) -> None:
        try:
            await self._say_line(text)
        except Exception:
            logger.exception("a line to the representative failed (%s)", self._ids())

    async def _stop_speaking(self) -> None:
        """Cut off a line still playing: the applicant is joining, or won't."""
        task, self.speaking = self.speaking, None
        if task is None:
            return
        if not task.done():
            task.cancel()
            self.step.flags.append("speech_cut")
        await asyncio.gather(task, return_exceptions=True)

    async def _fire_reading(self, trigger: Trigger, reading: PhaseReading) -> None:
        await self._fire(
            trigger,
            phase=reading.phase,
            confidence=round(reading.confidence, 2),
            source=reading.source,
        )
        if trigger == Trigger.HUMAN_DETECTED:
            await self._on_human()

    async def _fire(self, trigger: Trigger, **data: Any) -> Transition:
        """Move the state machine, then persist the state and log its event."""
        transition = self.sm.fire(trigger)
        self.step.transitions.append(transition)
        self._left(transition.from_state, transition.to_state)
        self.state_since_s = self.now_s()
        await self.deps.calls.set_state(self.call_id, transition.to_state)
        if transition.event_type is not None:
            await self._log(
                transition.event_type, _SUMMARIES[transition.event_type], **data
            )
        self._entered(transition.to_state)
        return transition

    def _left(self, old: CallState, new: CallState) -> None:
        if old == S.MENU and new != S.MENU:
            self.timers.cancel("menu_budget")
            self.menu_spent_s += self.now_s() - self.menu_entered_s
            self.escapes = 0
            self.menu_buffer.clear()
            self.forget_held()
            if self.ask is not None:
                self._drop_ask()
                self.step.flags.append("ask_abandoned")

    def _entered(self, new: CallState) -> None:
        match new:
            case S.MENU:
                self.menu_entered_s = self.now_s()
                remaining = max(self.config.menu_budget_s - self.menu_spent_s, 0.0)
                self.timers.start("menu_budget", remaining)
            case S.HOLD:
                self.executor.reset()
                if not self.hold_started:
                    self.hold_started = True
                    limit = self.config.hold_limit_s or self.job.max_hold_minutes * 60
                    self.timers.start("hold_limit", limit)
                elif self.hold_overdue:
                    self.timers.post_now("hold_limit")
            case S.BRIDGING:
                self.timers.cancel("hold_limit")
                self.timers.start("user_backstop", self.config.user_answer_backstop_s)
            case S.CONNECTED:
                self.timers.cancel("user_backstop")

    async def _retry_once[T](self, make: Callable[[], Awaitable[T]]) -> T:
        try:
            return await with_timeout(self.clock, make(), self.config.cleanup_timeout_s)
        except Exception:
            logger.warning(
                "wrap-up write failed; retrying once (%s)", self._ids(), exc_info=True
            )
            return await with_timeout(self.clock, make(), self.config.cleanup_timeout_s)
