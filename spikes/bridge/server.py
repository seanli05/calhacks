"""Spike server: the agency leg's stream, the STT forks after the bridge, and Twilio's
callbacks. One call at a time; state lives in this process, so never run --workers.

PYTHONPATH=backend uvicorn spikes.bridge.server:app --port 8000
"""

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal

from aiohttp import ClientError
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.stt import CartesiaSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner
from twilio.base.exceptions import TwilioRestException

from spikes.bridge.heard import HeardLog
from spikes.bridge.settings import load_settings
from spikes.bridge.twilio_calls import (
    agency_conference_twiml,
    hang_up,
    ring_user,
    update_call,
    user_conference_twiml,
    user_gate_twiml,
)

TWILIO_SAMPLE_RATE = 8000
INTRO = (
    "Hello, this is an automated assistant calling for the applicant. "
    "I'm connecting them to this call now, please hold for a moment."
)
CALL_BACK = (
    "I'm sorry, the account holder couldn't be reached right now. "
    "They will call back. Thank you, goodbye."
)
# Long enough for the call-back line to play before we hang up the agency leg.
CALL_BACK_PLAY_S = 7.0
TWILIO_ERRORS = (TwilioRestException, ClientError, TimeoutError)

settings = load_settings()
app = FastAPI()


@dataclass
class Bridge:
    """The one call this spike handles."""

    agency_sid: str | None = None
    worker: PipelineWorker | None = None  # the agency leg's /ws pipeline, until it ends
    bridge_at: float | None = None
    tasks: set[asyncio.Task] = field(default_factory=set)

    def since_bridge(self) -> str:
        if self.bridge_at is None:
            return "t=pre-bridge"
        return f"t=+{time.monotonic() - self.bridge_at:.1f}s"

    def background(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


state = Bridge()


def mark(what: str) -> None:
    logger.info(f"MARK {state.since_bridge()} {what}")


async def run_stream(
    websocket: WebSocket,
    *,
    stream: str,
    speaker: Literal["agency", "user"],
    speak: bool,
) -> None:
    """Run one Pipecat pipeline on a Twilio media stream until the stream ends."""
    transport_type, call_data = await parse_telephony_websocket(websocket)
    if transport_type != "twilio":
        logger.error(f"expected a Twilio stream, got {transport_type}")
        await websocket.close()
        return
    call_sid: str = call_data["call_id"]
    # Never auto hang up: /ws ends because we move the call, and forks end with it.
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )
    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=speak,
            add_wav_header=False,
            serializer=serializer,
        ),
    )
    processors: list[FrameProcessor] = [
        transport.input(),
        VADProcessor(vad_analyzer=SileroVADAnalyzer()),
        CartesiaSTTService(api_key=settings.cartesia_api_key),
        HeardLog(stream=stream, speaker=speaker, since_bridge=state.since_bridge),
    ]
    if speak:
        processors += [
            CartesiaTTSService(
                api_key=settings.cartesia_api_key,
                settings=CartesiaTTSService.Settings(
                    voice=settings.bridge_spike_voice_id
                ),
            ),
            transport.output(),
        ]
    worker = PipelineWorker(
        Pipeline(processors),
        params=PipelineParams(
            audio_in_sample_rate=TWILIO_SAMPLE_RATE,
            audio_out_sample_rate=TWILIO_SAMPLE_RATE,
        ),
    )
    runner = WorkerRunner(handle_sigint=False)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(
        _transport: FastAPIWebsocketTransport, _client: object
    ) -> None:
        mark(f"stream ended stream={stream} call_sid={call_sid}")
        await runner.cancel()

    if speak:
        state.agency_sid, state.worker, state.bridge_at = call_sid, worker, None
    mark(f"stream connected stream={stream} call_sid={call_sid}")
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        if speak and state.worker is worker:
            state.worker = None


@app.websocket("/ws")
async def agency_stream(websocket: WebSocket) -> None:
    """The agency leg before the bridge: two-way, so the agent can speak."""
    await websocket.accept()
    await run_stream(websocket, stream="pre", speaker="agency", speak=True)


@app.websocket("/ws-fork")
async def fork_stream(websocket: WebSocket) -> None:
    """A receive-only <Start><Stream> fork after the bridge; one per direction."""
    await websocket.accept()
    _, call_data = await parse_telephony_websocket(websocket)
    speaker = call_data.get("body", {}).get("speaker")
    if speaker not in ("agency", "user"):
        logger.error(f"fork without a known speaker parameter: {speaker!r}")
        await websocket.close()
        return
    await run_stream(websocket, stream=f"fork-{speaker}", speaker=speaker, speak=False)


@app.post("/bridge")
async def bridge() -> dict[str, str]:
    """Stand-in for "human detected": say the intro, then ring the user."""
    if state.agency_sid is None or state.worker is None:
        raise HTTPException(409, "no agency leg on /ws yet; run place_call first")
    state.bridge_at = time.monotonic()
    mark("bridge requested")
    await state.worker.queue_frame(TTSSpeakFrame(INTRO))
    try:
        user_sid = await ring_user(settings)
    except TWILIO_ERRORS as e:
        logger.error(f"ringing the user failed agency_sid={state.agency_sid}: {e!r}")
        raise HTTPException(502, "ringing the user failed") from e
    mark(f"user leg created user_sid={user_sid}")
    return {"agency_sid": state.agency_sid, "user_sid": user_sid}


@app.post("/twiml/user")
async def user_picked_up() -> Response:
    """Twilio fetches this on pickup, which may be voicemail: ask for a key first."""
    mark("user leg picked up (person or voicemail)")
    return Response(user_gate_twiml(settings), media_type="text/xml")


@app.post("/twiml/user/joined")
async def user_pressed_key(request: Request) -> Response:
    """The user pressed a key: join them, then move the agency leg."""
    form = await request.form()
    mark(f"user pressed key digits={form.get('Digits')}")
    if state.agency_sid is None:
        logger.error("user pressed a key but there is no agency leg")
        return Response("<Response><Hangup/></Response>", media_type="text/xml")
    state.background(move_agency_leg(state.agency_sid))
    return Response(
        user_conference_twiml(settings, state.agency_sid), media_type="text/xml"
    )


@app.post("/twiml/user/missed")
async def user_missed_gate() -> Response:
    """No key after pickup: voicemail, or the user put the phone down."""
    mark("user_unreachable reason=no_key_press")
    state.background(call_back_and_hang_up())
    return Response("<Response><Hangup/></Response>", media_type="text/xml")


async def move_agency_leg(agency_sid: str) -> None:
    try:
        await update_call(
            settings, agency_sid, agency_conference_twiml(settings, agency_sid)
        )
    except TWILIO_ERRORS as e:
        logger.error(f"moving the agency leg failed agency_sid={agency_sid}: {e!r}")
        return
    mark("agency leg update accepted")


@app.post("/status/user")
async def user_status(request: Request) -> Response:
    form = await request.form()
    status = form.get("CallStatus")
    mark(f"user leg status={status} duration={form.get('CallDuration')}")
    if status in ("busy", "no-answer", "failed", "canceled"):
        mark(f"user_unreachable reason={status}")
        state.background(call_back_and_hang_up())
    return Response(status_code=204)


async def call_back_and_hang_up() -> None:
    """Failure rule: tell the agency the account holder will call back, then end."""
    agency_sid, worker = state.agency_sid, state.worker
    if agency_sid is None or worker is None:
        logger.error("user unreachable but the agency leg is gone")
        return
    await worker.queue_frame(TTSSpeakFrame(CALL_BACK))
    await asyncio.sleep(CALL_BACK_PLAY_S)
    try:
        await hang_up(settings, agency_sid)
    except TWILIO_ERRORS as e:
        logger.error(f"hanging up the agency leg failed agency_sid={agency_sid}: {e!r}")
        return
    mark("agency leg hung up")


@app.post("/status/conference")
async def conference_status(request: Request) -> Response:
    form = await request.form()
    call_sid = form.get("CallSid")
    who = (
        "-"
        if call_sid is None
        else "agency"
        if call_sid == state.agency_sid
        else "user"
    )
    mark(f"conference {form.get('StatusCallbackEvent')} participant={who}")
    return Response(status_code=204)
