"""The ears of the real phone line: Pipecat frames in, `LineEvent`s out.

`TurnAssembler` is the logic, pure and driven by timestamps so it tests without
audio. `LineListener` is the Pipecat processor around it: it sits after voice
activity detection and speech-to-text, feeds the assembler, and also resolves
the playback marks that tell `say()` its audio has played.

Turns (the contract in `line.py`): voice activity opens one with `SpeechStarted`.
Speech-to-text fragments are joined until the line has been quiet `merge_gap_s`,
then the turn closes with one `Heard`, or a `NonSpeech` if it had no words. A
turn longer than `max_turn_s` is cut there so a long menu isn't held back.

Between turns, `NonSpeech` reports the quiet stretch every `nonspeech_every_s`,
with its running length, as music when most of it was loud, else silence.

The numbers are first guesses from how phone lines behave in general, to tune
on real calls, never to one line's pauses (CLAUDE.md → the mock agency).
"""

import asyncio
import logging
import math
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    SystemFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.phone.line import Heard, LineEvent, NonSpeech, SpeechStarted
from app.phone.ports import LineClosed

logger = logging.getLogger(__name__)

LOUD_RMS = 200
"""16-bit RMS above which a quiet stretch counts as sound (about -44 dBFS). An
idle phone line sits well below; hold music well above."""
_TICK_S = 0.1


@dataclass(frozen=True)
class TurnTiming:
    merge_gap_s: float = 1.0
    """Quiet that closes a turn. Longer than the pauses between a menu's options,
    short enough for the < 5 s human → ring target."""
    final_grace_s: float = 0.5
    """Extra wait for speech-to-text's last fragment after the gap. Cartesia sends
    nothing for a turn with no words, so a wordless turn waits all of it."""
    max_turn_s: float = 25.0
    nonspeech_every_s: float = 5.0


class TurnAssembler:
    """Turns voice activity, transcripts, and loudness into line events. Every
    method takes `now` (monotonic seconds) and returns the events to emit."""

    def __init__(self, now: float, timing: TurnTiming | None = None) -> None:
        self._timing = timing or TurnTiming()
        self._in_turn = False
        self._speaking = False
        self._turn_start = now
        self._last_stop: float | None = None
        self._awaiting_final = False
        self._fragments: list[str] = []
        self._stretch_start = now
        self._stretch_loud = 0
        self._stretch_frames = 0
        self._next_report = self._timing.nonspeech_every_s
        self._music_before_turn = False

    def speech_started(self, now: float) -> list[LineEvent]:
        self._speaking = True
        if self._in_turn:
            return []
        self._music_before_turn = self._stretch_sound() == "music"
        self._open_turn(now)
        return [SpeechStarted()]

    def speech_stopped(self, now: float) -> list[LineEvent]:
        self._speaking = False
        self._last_stop = now
        self._awaiting_final = True
        return []

    def transcript(self, text: str, now: float) -> list[LineEvent]:
        text = text.strip()
        self._awaiting_final = False
        if not text:
            return []
        if not self._in_turn:
            # Speech-to-text was later than the grace: a turn of its own.
            return [SpeechStarted(), Heard(text=text)]
        self._fragments.append(text)
        return []

    def audio(self, rms: float, now: float) -> list[LineEvent]:
        if self._in_turn:
            return []
        self._stretch_frames += 1
        self._stretch_loud += rms >= LOUD_RMS
        return []

    def tick(self, now: float) -> list[LineEvent]:
        timing = self._timing
        if not self._in_turn:
            length = now - self._stretch_start
            if length < self._next_report:
                return []
            self._next_report += timing.nonspeech_every_s
            return [NonSpeech(sound=self._stretch_sound(), seconds=length)]
        if self._speaking:
            if now - self._turn_start >= timing.max_turn_s and self._fragments:
                heard = Heard(text=" ".join(self._fragments))
                self._open_turn(now)
                return [heard, SpeechStarted()]
            return []
        if self._last_stop is None:
            return []
        quiet = now - self._last_stop
        if quiet < timing.merge_gap_s:
            return []
        if self._awaiting_final and quiet < timing.merge_gap_s + timing.final_grace_s:
            return []
        return [self._close_turn(now)]

    def flush(self, now: float) -> list[LineEvent]:
        """The stream is ending: close a half-built turn."""
        return [self._close_turn(now)] if self._in_turn else []

    def _open_turn(self, now: float) -> None:
        self._in_turn = True
        self._turn_start = now
        self._last_stop = None
        self._awaiting_final = False
        self._fragments = []

    def _close_turn(self, now: float) -> LineEvent:
        self._in_turn = False
        text = " ".join(self._fragments)
        self._fragments = []
        self._stretch_start = self._last_stop if self._last_stop is not None else now
        self._stretch_loud = self._stretch_frames = 0
        self._next_report = self._timing.nonspeech_every_s
        if text:
            return Heard(text=text)
        sound = "music" if self._music_before_turn else "silence"
        return NonSpeech(sound=sound, seconds=max(now - self._turn_start, 0.1))

    def _stretch_sound(self) -> str:
        if self._stretch_frames and self._stretch_loud * 2 >= self._stretch_frames:
            return "music"
        return "silence"


def rms(pcm16: bytes) -> float:
    samples = array("h", pcm16[: len(pcm16) - len(pcm16) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


@dataclass
class PlaybackMarkFrame(SystemFrame):
    """Twilio played everything sent before the mark named `mark`."""

    mark: str = ""


class LineListener(FrameProcessor):
    """Sits after speech-to-text and before text-to-speech. Emits line events
    through `emit` and passes on everything the speaking side needs."""

    def __init__(
        self,
        emit: Callable[[LineEvent], None],
        *,
        timing: TurnTiming | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._emit = emit
        self._clock = clock
        self._turns = TurnAssembler(clock(), timing)
        self._marks: dict[str, asyncio.Future[None]] = {}
        self._ticker: asyncio.Task[None] | None = None

    def expect_mark(self, name: str) -> asyncio.Future[None]:
        future = asyncio.get_running_loop().create_future()
        self._marks[name] = future
        return future

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction is not FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return
        now = self._clock()
        match frame:
            case InputAudioRawFrame():
                self._send(self._turns.audio(rms(frame.audio), now))
                return  # the speaking side has no use for the agency's audio
            case PlaybackMarkFrame(mark=mark):
                future = self._marks.pop(mark, None)
                if future is not None and not future.done():
                    future.set_result(None)
                return
            case VADUserStartedSpeakingFrame():
                self._send(self._turns.speech_started(now))
            case VADUserStoppedSpeakingFrame():
                self._send(self._turns.speech_stopped(now))
            case TranscriptionFrame(text=text):
                self._send(self._turns.transcript(text, now))
            case InterimTranscriptionFrame():
                return
            case StartFrame():
                self._ticker = self.create_task(self._tick())
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        if self._ticker is not None:
            await self.cancel_task(self._ticker)
            self._ticker = None
        self._send(self._turns.flush(self._clock()))
        for future in self._marks.values():
            if not future.done():
                future.set_exception(LineClosed("the stream ended"))
        self._marks.clear()
        await super().cleanup()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(_TICK_S)
            self._send(self._turns.tick(self._clock()))

    def _send(self, events: list[LineEvent]) -> None:
        for event in events:
            self._emit(event)
