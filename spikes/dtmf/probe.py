"""MenuProbe: waits for the mock line's main menu to finish, presses "2" one way,
and checks whether the appointment menu follows."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum

from loguru import logger
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import (
    EndWorkerFrame,
    Frame,
    OutputDTMFUrgentFrame,
    StartFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class Mode(StrEnum):
    # Over Twilio Media Streams this becomes in-band tone audio (no native DTMF out).
    DTMF = "dtmf"
    SPEAK = "speak"
    # Call update with <Play digits>, then a fresh <Stream> (leg 2) to hear the result.
    REST = "rest"


class Phase(StrEnum):
    WAIT_MAIN_MENU = "wait_main_menu"
    ARMED = "armed"
    WAIT_APPOINTMENT = "wait_appointment"
    DONE = "done"


# Last sentence of the main menu: "To hear these options again, press 9."
# STT sometimes splits it and drops "press" ("...options again," + "9."), so match either half.
MAIN_MENU_END = ("press 9", "press nine", "options again")
# Any line of the appointment menu; none of these appear in the main menu.
APPOINTMENT_MENU = ("biometrics", "asylum interview", "naturalization interview")
# Main menu again (key not received), invalid option, or the line's no-input reprompt.
NOT_ACCEPTED = (
    "check the status of a case",
    "not a valid option",
    "didn't get a response",
)

# Extra silence after VAD stop before acting, so we don't act between two prompt sentences
# (or between "options again," and "press 9"). Well under the line's 12 s no-input timer.
QUIET_BEFORE_ACTING_S = 1.0
MAIN_MENU_TIMEOUT_S = 45.0
RESULT_TIMEOUT_S = 20.0

# Sends the REST call update; returns False if Twilio refused or timed out.
RedirectHook = Callable[[], Awaitable[bool]]


def heard_any(heard: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in heard for phrase in phrases)


class MenuProbe(FrameProcessor):
    def __init__(
        self,
        *,
        mode: Mode,
        leg: str,
        call_sid: str,
        redirect: RedirectHook | None = None,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._leg = leg
        self._call_sid = call_sid
        self._redirect = redirect
        # Rest leg 2 joins after the digits were played, so it only checks the result.
        self._phase = Phase.WAIT_APPOINTMENT if leg == "2" else Phase.WAIT_MAIN_MENU
        self._heard = ""
        self._remote_speaking = False
        self._connected_at = time.monotonic()
        self._acted_at: float | None = None
        self._timer: asyncio.Task | None = None
        self._quiet: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._start_timer()
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            self._remote_speaking = True
            await self._cancel(self._quiet)
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._remote_speaking = False
            if self._phase is Phase.ARMED:
                self._schedule_act()
        elif isinstance(frame, TranscriptionFrame):
            await self._on_transcript(frame.text)

    async def cleanup(self) -> None:
        await self._cancel(self._timer)
        await self._cancel(self._quiet)
        await super().cleanup()

    def _start_timer(self) -> None:
        self._connected_at = time.monotonic()
        timeout = (
            RESULT_TIMEOUT_S
            if self._phase is Phase.WAIT_APPOINTMENT
            else MAIN_MENU_TIMEOUT_S
        )
        reason = (
            "no appointment menu"
            if self._phase is Phase.WAIT_APPOINTMENT
            else "no main menu"
        )
        self._timer = self.create_task(self._fail_after(timeout, reason))

    async def _on_transcript(self, text: str) -> None:
        now = datetime.now().isoformat(timespec="milliseconds")
        logger.info(f"[{now}] [+{self._elapsed():6.2f}s] heard: {text}")
        self._heard += " " + text.lower()

        if self._phase is Phase.WAIT_MAIN_MENU and heard_any(
            self._heard, MAIN_MENU_END
        ):
            self._phase = Phase.ARMED
            logger.info(
                f"main menu finished; armed mode={self._mode} call_sid={self._call_sid}"
            )
            # The VAD stop for this sentence usually lands before its transcript.
            if not self._remote_speaking:
                self._schedule_act()
        elif self._phase is Phase.WAIT_APPOINTMENT:
            if heard_any(self._heard, APPOINTMENT_MENU):
                await self._finish(passed=True, reason="heard appointment menu")
            elif heard_any(self._heard, NOT_ACCEPTED):
                await self._finish(passed=False, reason="line did not take the choice")

    def _schedule_act(self) -> None:
        if self._quiet is None or self._quiet.done():
            self._quiet = self.create_task(self._act_when_quiet())

    async def _act_when_quiet(self) -> None:
        await asyncio.sleep(QUIET_BEFORE_ACTING_S)
        if self._phase is Phase.ARMED and not self._remote_speaking:
            await self._act()

    async def _act(self) -> None:
        await self._cancel(self._timer)
        self._phase = Phase.WAIT_APPOINTMENT
        self._heard = ""
        self._acted_at = time.monotonic()
        logger.info(
            f"acting mode={self._mode} at +{self._elapsed():.2f}s call_sid={self._call_sid}"
        )

        match self._mode:
            case Mode.DTMF:
                await self.push_frame(OutputDTMFUrgentFrame(button=KeypadEntry.TWO))
            case Mode.SPEAK:
                await self.push_frame(TTSSpeakFrame("two"))
            case Mode.REST:
                if self._redirect is None or not await self._redirect():
                    await self._finish(passed=False, reason="rest call update failed")
                    return
                # Twilio now drops this stream; leg 2 reports the result.
                self._phase = Phase.DONE
                logger.info(
                    f"rest update sent; leg 1 done, waiting for leg 2 call_sid={self._call_sid}"
                )
                return

        self._timer = self.create_task(
            self._fail_after(RESULT_TIMEOUT_S, "no appointment menu")
        )

    async def _fail_after(self, seconds: float, reason: str) -> None:
        await asyncio.sleep(seconds)
        self._timer = None  # don't let _finish cancel the task it's running in
        await self._finish(passed=False, reason=f"timeout: {reason}")

    async def _finish(self, *, passed: bool, reason: str) -> None:
        if self._phase is Phase.DONE:
            return
        self._phase = Phase.DONE
        await self._cancel(self._timer)
        latency = (
            f"{time.monotonic() - self._acted_at:.2f}s" if self._acted_at else "n/a"
        )
        logger.info(
            f"RESULT {'PASS' if passed else 'FAIL'} mode={self._mode} leg={self._leg} "
            f"reason={reason!r} latency_after_action={latency} at=+{self._elapsed():.2f}s "
            f"call_sid={self._call_sid} heard_after_action={self._heard.strip()!r}"
        )
        # Graceful end; the serializer's auto hang-up then completes the call.
        await self.push_frame(EndWorkerFrame())

    async def _cancel(self, task: asyncio.Task | None) -> None:
        if task is not None and not task.done() and task is not asyncio.current_task():
            await self.cancel_task(task)

    def _elapsed(self) -> float:
        return time.monotonic() - self._connected_at
