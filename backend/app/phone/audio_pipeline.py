"""One Twilio media stream's Pipecat pipeline: the ears and the mouth of the line.

    transport.input → VAD (Silero) → speech-to-text (Cartesia Ink) → LineListener
                    → text-to-speech (Cartesia Sonic) → transport.output

After the bridge, each leg also runs a listen-only fork (`run_fork`): the same ears
with no mouth, whose finished turns become `Overheard` lines for the transcript.

No model decides anything here; the call runner does. Learned from
`spikes/dtmf/server.py`, not imported from it. What the source taught us:

- `say()` waits for a Twilio `mark` sent after the speech. Pipecat sends audio
  faster than it plays, so its own "bot stopped speaking" comes early. The TTS
  service queues frames sent after a `TTSSpeakFrame` behind that speech's audio,
  and the serializer below turns Twilio's echo of the mark into a frame.
- `auto_hang_up` is off: the pipeline ends on every `press_keys` reconnect, and
  only `TwilioTelephony.hang_up` ends the call.
- The worker's idle timeout is off: hold music makes no transcripts, and the
  default would cancel the stream after 5 minutes on hold.
- Nothing records audio (C29).
"""

import asyncio
import json
import logging
from itertools import count
from typing import Literal

from fastapi import WebSocket
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import Frame, OutputTransportMessageFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.stt import CartesiaSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel

from app.phone.listener import LineListener, PlaybackMarkFrame, overheard
from app.phone.twilio_line import TwilioTelephony
from app.settings import Settings

logger = logging.getLogger(__name__)

TWILIO_SAMPLE_RATE = 8000
VAD_STOP_S = 0.5
"""Silence that ends a speech chunk, and makes speech-to-text finalize. Pipecat's
0.2 s split menu sentences mid-phrase; the listener joins chunks into turns."""
VAD_START_S = 0.5
"""Speech this long before it counts as speech, so breaths and clicks don't open a
turn (and hold back a menu answer). Risk: a rep's bare "Hello?" is about this
long; if live calls miss one, 0.3 s is the fallback."""
START_TIMEOUT_S = 10.0
_marks = count(1)


class TwilioStart(BaseModel):
    stream_sid: str
    call_sid: str


async def read_twilio_start(websocket: WebSocket) -> TwilioStart:
    """Read Twilio's `connected` and `start` messages. Raises `TimeoutError`, or
    `ValueError` if the stream says something else first."""
    async with asyncio.timeout(START_TIMEOUT_S):
        while True:
            message = json.loads(await websocket.receive_text())
            match message.get("event"):
                case "connected":
                    continue
                case "start":
                    start = message.get("start") or {}
                    return TwilioStart(
                        stream_sid=start.get("streamSid", ""),
                        call_sid=start.get("callSid", ""),
                    )
                case other:
                    raise ValueError(f"expected a stream start, got {other!r}")


class MarkingTwilioSerializer(TwilioFrameSerializer):
    """Twilio's serializer, plus Twilio's `mark` echoes as `PlaybackMarkFrame`."""

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, str) and '"mark"' in data:
            message = json.loads(data)
            if message.get("event") == "mark":
                return PlaybackMarkFrame(mark=message.get("mark", {}).get("name", ""))
        return await super().deserialize(data)


class PipecatStream:
    """The `AudioStream` the line speaks through."""

    def __init__(
        self,
        worker: PipelineWorker,
        runner: WorkerRunner,
        listener: LineListener,
        stream_sid: str,
    ) -> None:
        self._worker = worker
        self._runner = runner
        self._listener = listener
        self._stream_sid = stream_sid

    async def speak(self, text: str) -> None:
        mark = f"say-{next(_marks)}"
        played = self._listener.expect_mark(mark)
        await self._worker.queue_frames(
            [
                TTSSpeakFrame(text),
                OutputTransportMessageFrame(
                    message={
                        "event": "mark",
                        "streamSid": self._stream_sid,
                        "mark": {"name": mark},
                    }
                ),
            ]
        )
        await played

    async def interrupt(self) -> None:
        await self._listener.broadcast_interruption()

    async def close(self) -> None:
        await self._runner.cancel()


def _transport(
    websocket: WebSocket, start: TwilioStart, *, speaks: bool
) -> FastAPIWebsocketTransport:
    return FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=speaks,
            add_wav_header=False,
            serializer=MarkingTwilioSerializer(
                stream_sid=start.stream_sid,
                call_sid=start.call_sid,
                params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
            ),
        ),
    )


def _ears(settings: Settings) -> list[FrameProcessor]:
    """Voice activity, then speech-to-text."""
    return [
        VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(start_secs=VAD_START_S, stop_secs=VAD_STOP_S)
            )
        ),
        CartesiaSTTService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaSTTService.Settings(
                model=settings.cartesia_stt_model, language="en"
            ),
        ),
    ]


def _worker(processors: list[FrameProcessor]) -> PipelineWorker:
    return PipelineWorker(
        Pipeline(processors),
        params=PipelineParams(
            audio_in_sample_rate=TWILIO_SAMPLE_RATE,
            audio_out_sample_rate=TWILIO_SAMPLE_RATE,
        ),
        idle_timeout_secs=None,
        enable_rtvi=False,
    )


def _runner_for(transport: FastAPIWebsocketTransport) -> WorkerRunner:
    """A runner that stops when Twilio closes the websocket."""
    runner = WorkerRunner(handle_sigint=False)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(
        _transport: FastAPIWebsocketTransport, _client: object
    ) -> None:
        await runner.cancel()

    return runner


async def _run(runner: WorkerRunner, worker: PipelineWorker) -> None:
    try:
        await runner.add_workers(worker)
        await runner.run()
    except asyncio.CancelledError:
        # `PipecatStream.close` cancels the runner, which raises here; that's the
        # normal end of a stream. Only a cancel of this task itself goes on.
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            raise


async def run_stream(
    websocket: WebSocket, start: TwilioStart, line: TwilioTelephony, settings: Settings
) -> None:
    """Run the pipeline for one stream until the websocket closes or the line
    closes it."""
    listener = LineListener(line.emit)
    transport = _transport(websocket, start, speaks=True)
    worker = _worker(
        [
            transport.input(),
            *_ears(settings),
            listener,
            CartesiaTTSService(
                api_key=settings.cartesia_api_key,
                settings=CartesiaTTSService.Settings(
                    model=settings.cartesia_tts_model,
                    voice=settings.cartesia_agent_voice_id,
                ),
            ),
            transport.output(),
        ]
    )
    runner = _runner_for(transport)
    seq = line.attach_stream(
        PipecatStream(worker, runner, listener, start.stream_sid), start.call_sid
    )
    if seq is None:
        logger.warning("stream refused by its line (sid=%s)", start.call_sid)
        await websocket.close()
        return
    try:
        await _run(runner, worker)
    finally:
        line.detach_stream(seq)


async def run_fork(
    websocket: WebSocket,
    start: TwilioStart,
    line: TwilioTelephony,
    speaker: Literal["agency", "user"],
    settings: Settings,
) -> None:
    """Run a listen-only fork of one leg after the bridge, until Twilio ends it.
    The line owns nothing of it: the legs' status callbacks say when the call ends,
    and Twilio closes the fork with its leg."""
    if not line.attach_fork(speaker, start.call_sid):
        logger.warning("fork refused by its line (sid=%s)", start.call_sid)
        await websocket.close()
        return
    transport = _transport(websocket, start, speaks=False)
    worker = _worker(
        [
            transport.input(),
            *_ears(settings),
            LineListener(overheard(line.emit, speaker)),
        ]
    )
    await _run(_runner_for(transport), worker)
