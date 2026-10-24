"""Spike server: one Pipecat pipeline per Twilio Media Stream on /ws.

PYTHONPATH=backend uvicorn spikes.dtmf.server:app --port 8000
"""

from aiohttp import ClientError
from fastapi import FastAPI, WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
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

from spikes.dtmf.probe import MenuProbe, Mode
from spikes.dtmf.settings import load_settings, stream_url
from spikes.dtmf.twilio_calls import stream_twiml, update_call

TWILIO_SAMPLE_RATE = 8000

settings = load_settings()
app = FastAPI()


@app.websocket("/ws")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    transport_type, call_data = await parse_telephony_websocket(websocket)
    if transport_type != "twilio":
        logger.error(f"expected a Twilio stream, got {transport_type}")
        await websocket.close()
        return

    call_sid: str = call_data["call_id"]
    params = call_data.get("body") or {}
    try:
        mode = Mode(params.get("mode", ""))
    except ValueError:
        logger.error(f"unknown mode {params.get('mode')!r} call_sid={call_sid}")
        await websocket.close()
        return
    leg: str = params.get("leg", "1")
    if mode is Mode.SPEAK and not settings.dtmf_spike_voice_id:
        logger.error(f"speak mode needs DTMF_SPIKE_VOICE_ID call_sid={call_sid}")
        await websocket.close()
        return
    logger.info(f"stream connected mode={mode} leg={leg} call_sid={call_sid}")

    # Rest leg 1 ends because we redirect the call; hanging up then would kill leg 2.
    redirecting_leg = mode is Mode.REST and leg == "1"
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        params=TwilioFrameSerializer.InputParams(auto_hang_up=not redirecting_leg),
    )
    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    async def redirect() -> bool:
        twiml = stream_twiml(
            stream_url(settings), mode=Mode.REST, leg="2", play_digits="w2"
        )
        try:
            await update_call(settings, call_sid, twiml)
        except (TwilioRestException, ClientError, TimeoutError) as e:
            logger.error(f"rest call update failed call_sid={call_sid}: {e!r}")
            return False
        return True

    probe = MenuProbe(
        mode=mode,
        leg=leg,
        call_sid=call_sid,
        redirect=redirect if redirecting_leg else None,
    )
    processors: list[FrameProcessor] = [
        transport.input(),
        VADProcessor(vad_analyzer=SileroVADAnalyzer()),
        CartesiaSTTService(api_key=settings.cartesia_api_key),
        probe,
    ]
    if mode is Mode.SPEAK:
        processors.append(
            CartesiaTTSService(
                api_key=settings.cartesia_api_key,
                settings=CartesiaTTSService.Settings(
                    voice=settings.dtmf_spike_voice_id
                ),
            )
        )
    processors.append(transport.output())

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
        logger.info(f"stream disconnected mode={mode} leg={leg} call_sid={call_sid}")
        await runner.cancel()

    await runner.add_workers(worker)
    await runner.run()
