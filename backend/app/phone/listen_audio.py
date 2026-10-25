"""What the user hears when they sit in: the call, mixed, on a leg of its own.

The agency leg runs on `<Connect><Stream>`, so it can't join a conference while the
agent still speaks and presses keys on it. Instead the user's listen leg streams
too, and we write the call into it:

    agency stream:  transport.input → ListenTap("agency") → … → TTS
                    → ListenTap("agent") → transport.output
                                  ↓
                             ListenMixer → ListenSink → the listen leg's stream

The agency's frames arrive in real time (Twilio sends 20 ms every 20 ms, hold music
and silence included), so they set the pace: each one goes out with as much of the
agent's speech laid over it. Text-to-speech comes faster than it plays, so the
agent's audio waits in a buffer until then. While the agent's stream is swapped for
a key press there are no agency frames, and the user hears a moment's silence.

Nothing the user says is read or forwarded, so the agency can't hear them (rule 3),
and nothing records (C29). The agency pipeline never waits on the listener: the
sink drops audio it can't send in time.
"""

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Literal

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from pipecat.audio.utils import create_stream_resampler, mix_audio, pcm_to_ulaw
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

if TYPE_CHECKING:
    from app.phone.audio_pipeline import TwilioStart
    from app.phone.twilio_line import TwilioTelephony

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
"""Twilio's rate, which the agency pipeline runs at both ways."""
MAX_AGENT_S = 60.0
"""Agent speech buffered ahead of the agency's frames. More than any fixed line
takes to say; past it, the newest audio is dropped."""
SINK_CHUNKS = 50
"""About a second of 20 ms chunks queued for the listen leg before dropping."""


class ListenSink:
    """Writes PCM chunks to one listen leg's media stream, as Twilio `media`
    messages, from its own task (`run`)."""

    def __init__(
        self, websocket: WebSocket, stream_sid: str, *, max_chunks: int = SINK_CHUNKS
    ) -> None:
        self._websocket = websocket
        self._stream_sid = stream_sid
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max_chunks)
        self.dropped = 0

    def send(self, pcm: bytes) -> None:
        try:
            self._queue.put_nowait(pcm)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 500 == 0:
                logger.debug("listen leg behind; dropped %d chunks", self.dropped)

    async def run(self) -> None:
        resampler = create_stream_resampler()
        while True:
            pcm = await self._queue.get()
            ulaw = await pcm_to_ulaw(pcm, SAMPLE_RATE, SAMPLE_RATE, resampler)
            await self._websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": self._stream_sid,
                        "media": {"payload": base64.b64encode(ulaw).decode()},
                    }
                )
            )


class ListenMixer:
    """The call as the listener hears it. One per line, so it outlives the agent's
    stream swaps; it does nothing while no sink is attached."""

    def __init__(self, *, max_agent_s: float = MAX_AGENT_S) -> None:
        self._sink: ListenSink | None = None
        self._agent = bytearray()
        self._max_agent_bytes = int(max_agent_s * SAMPLE_RATE) * 2

    @property
    def listening(self) -> bool:
        return self._sink is not None

    def attach(self, sink: ListenSink) -> None:
        self._sink = sink
        self._agent.clear()

    def detach(self, sink: ListenSink) -> None:
        if self._sink is sink:
            self._sink = None
            self._agent.clear()

    def agency_audio(self, pcm: bytes) -> None:
        if self._sink is None:
            return
        part = bytes(self._agent[: len(pcm)])
        del self._agent[: len(pcm)]
        self._sink.send(mix_audio(pcm, part) if part else pcm)

    def agent_audio(self, pcm: bytes) -> None:
        if self._sink is None:
            return
        room = self._max_agent_bytes - len(self._agent)
        self._agent += pcm[: max(room, 0)]

    def interrupt(self) -> None:
        """The agent was cut off: what it hadn't said yet isn't said."""
        self._agent.clear()


class ListenTap(FrameProcessor):
    """Copies one side's audio into the mixer and passes every frame on unchanged.
    `agency` sits right after the transport's input, `agent` right before its
    output."""

    def __init__(self, mixer: ListenMixer, side: Literal["agency", "agent"]) -> None:
        super().__init__()
        self._mixer = mixer
        self._side = side
        self._warned = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction is FrameDirection.DOWNSTREAM:
            match self._side, frame:
                case "agency", InputAudioRawFrame() if self._fits(frame):
                    self._mixer.agency_audio(frame.audio)
                case "agent", OutputAudioRawFrame() if self._fits(frame):
                    self._mixer.agent_audio(frame.audio)
                case "agent", InterruptionFrame():
                    self._mixer.interrupt()
        await self.push_frame(frame, direction)

    def _fits(self, frame: AudioRawFrame) -> bool:
        if frame.sample_rate == SAMPLE_RATE and frame.num_channels == 1:
            return True
        if not self._warned:
            self._warned = True
            logger.warning(
                "%s audio at %d Hz x%d skipped for the listener",
                self._side,
                frame.sample_rate,
                frame.num_channels,
            )
        return False


async def run_listener(
    websocket: WebSocket, start: "TwilioStart", line: "TwilioTelephony"
) -> None:
    """Serve one listen leg's stream until Twilio ends it or a write fails. What
    comes in from the user is read only to notice the end, never kept or passed on."""
    sink = ListenSink(websocket, start.stream_sid)
    if not line.attach_listener(sink, start.call_sid):
        logger.warning("listen stream refused by its line (sid=%s)", start.call_sid)
        await websocket.close()
        return
    writer = asyncio.create_task(sink.run())
    reader = asyncio.create_task(_until_stop(websocket))
    try:
        done, _ = await asyncio.wait(
            {writer, reader}, return_when=asyncio.FIRST_COMPLETED
        )
        if writer in done and (exc := writer.exception()) is not None:
            logger.info("listen stream write failed: %s", type(exc).__name__)
    finally:
        line.detach_listener(sink)
        for task in (writer, reader):
            task.cancel()
        await asyncio.gather(writer, reader, return_exceptions=True)


async def _until_stop(websocket: WebSocket) -> None:
    try:
        while True:
            message = await websocket.receive_text()
            if '"stop"' in message and json.loads(message).get("event") == "stop":
                return
    except WebSocketDisconnect:
        return
