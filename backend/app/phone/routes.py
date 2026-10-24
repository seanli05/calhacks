"""Twilio's ways into a live call: status callbacks, the applicant's join gate,
the media stream, and the listen-only forks after the bridge.

All of them find the call's line in `twilio_line.LINES` by the `call_id` in the
path, and all check Twilio's signature with the relay's helper. Twilio signs the
websocket handshake against the `wss://` URL it was given, so streams are checked
against that form too. Unknown calls and bad signatures are refused and logged
with the call_id only. A gate callback for a call that's over gets TwiML that
hangs the applicant up.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import ValidationError

from app.phone.audio_pipeline import (
    TwilioStart,
    read_twilio_start,
    run_fork,
    run_stream,
)
from app.phone.twilio_line import LINES, TwilioTelephony
from app.phone.twilio_rest import hang_up_twiml
from app.phone.twilio_urls import (
    FORK_PATH,
    STATUS_PATH,
    STREAM_PATH,
    USER_JOINED_PATH,
    USER_MISSED_PATH,
    USER_STATUS_PATH,
)
from app.relay.signature import is_valid_twilio_request
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_POLICY_VIOLATION = 1008


async def _signed_params(
    request: Request, settings: Settings, call_id: str, what: str
) -> dict[str, str]:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    if not is_valid_twilio_request(request, params, settings):
        logger.warning("Rejected %s: bad Twilio signature (call_id=%s)", what, call_id)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return params


def _twiml(twiml: str) -> Response:
    return Response(twiml, media_type="text/xml")


@router.post(STATUS_PATH)
async def call_status(
    call_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    params = await _signed_params(request, settings, call_id, "call status")
    line = LINES.get(call_id)
    if line is None:
        # A late callback for a call that's over, or a restart: nothing to tell.
        logger.info("Call status for no live line (call_id=%s)", call_id)
    else:
        line.on_status(params.get("CallSid", ""), params.get("CallStatus", ""))
    return Response(status_code=204)


@router.post(USER_STATUS_PATH)
async def user_status(
    call_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    params = await _signed_params(request, settings, call_id, "applicant status")
    line = LINES.get(call_id)
    if line is None:
        logger.info("Applicant status for no live line (call_id=%s)", call_id)
    else:
        line.on_user_status(params.get("CallSid", ""), params.get("CallStatus", ""))
    return Response(status_code=204)


@router.post(USER_JOINED_PATH)
async def user_joined(
    call_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """The join gate's `<Gather>` action: the applicant pressed a key."""
    params = await _signed_params(request, settings, call_id, "applicant key press")
    line = LINES.get(call_id)
    if line is None:
        logger.info("Applicant key press for no live line (call_id=%s)", call_id)
        return _twiml(hang_up_twiml())
    return _twiml(line.user_pressed_key(params.get("CallSid", "")))


@router.post(USER_MISSED_PATH)
async def user_missed(
    call_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """The join gate's fall-through: no key in time."""
    params = await _signed_params(request, settings, call_id, "applicant no key")
    line = LINES.get(call_id)
    if line is None:
        return _twiml(hang_up_twiml())
    return _twiml(line.user_missed_gate(params.get("CallSid", "")))


def _signed_stream(websocket: WebSocket, settings: Settings) -> bool:
    """The relay's helper reads only the headers and the URL path, which a
    websocket handshake has too."""
    if is_valid_twilio_request(websocket, {}, settings):
        return True
    as_wss = "wss://" + settings.public_base_url.split("://", 1)[-1]
    wss_settings = settings.model_copy(update={"public_base_url": as_wss})
    return is_valid_twilio_request(websocket, {}, wss_settings)


async def _open_stream(
    websocket: WebSocket, call_id: str, settings: Settings
) -> tuple[TwilioTelephony, TwilioStart] | None:
    """Accept a signed stream for a live line and read its start, or refuse it."""
    line = LINES.get(call_id)
    if line is None or not _signed_stream(websocket, settings):
        logger.warning(
            "Refused media stream (call_id=%s, known=%s)", call_id, line is not None
        )
        await websocket.close(code=_POLICY_VIOLATION)
        return None
    await websocket.accept()
    try:
        start = await read_twilio_start(websocket)
    except (TimeoutError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Media stream never started (call_id=%s): %s", call_id, exc)
        await websocket.close(code=_POLICY_VIOLATION)
        return None
    except WebSocketDisconnect:
        logger.info("Media stream closed before it started (call_id=%s)", call_id)
        return None
    return line, start


@router.websocket(STREAM_PATH)
async def call_stream(websocket: WebSocket, call_id: str) -> None:
    settings = get_settings()
    if opened := await _open_stream(websocket, call_id, settings):
        line, start = opened
        await run_stream(websocket, start, line, settings)


@router.websocket(FORK_PATH)
async def call_fork(websocket: WebSocket, call_id: str, speaker: str) -> None:
    """A listen-only fork of one leg after the bridge (`<Start><Stream>`)."""
    match speaker:
        case "agency" | "user":
            settings = get_settings()
            if opened := await _open_stream(websocket, call_id, settings):
                line, start = opened
                await run_fork(websocket, start, line, speaker, settings)
        case _:
            logger.warning("Refused fork for speaker %r (call_id=%s)", speaker, call_id)
            await websocket.close(code=_POLICY_VIOLATION)
