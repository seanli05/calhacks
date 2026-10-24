"""Twilio's two ways into a live call: status callbacks and the media stream.

Both find the call's line in `twilio_line.LINES` by the `call_id` in the path, and
both check Twilio's signature with the relay's helper. Twilio signs the websocket
handshake against the `wss://` URL it was given, so the stream is checked against
that form too. Unknown calls and bad signatures are refused and logged with the
call_id only.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import ValidationError

from app.phone.audio_pipeline import read_twilio_start, run_stream
from app.phone.twilio_line import LINES, STATUS_PATH, STREAM_PATH
from app.relay.signature import is_valid_twilio_request
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_POLICY_VIOLATION = 1008


@router.post(STATUS_PATH)
async def call_status(
    call_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    if not is_valid_twilio_request(request, params, settings):
        logger.warning(
            "Rejected call status: bad Twilio signature (call_id=%s)", call_id
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    line = LINES.get(call_id)
    if line is None:
        # A late callback for a call that's over, or a restart: nothing to tell.
        logger.info("Call status for no live line (call_id=%s)", call_id)
    else:
        line.on_status(params.get("CallSid", ""), params.get("CallStatus", ""))
    return Response(status_code=204)


def _signed_stream(websocket: WebSocket, settings: Settings) -> bool:
    """The relay's helper reads only the headers and the URL path, which a
    websocket handshake has too."""
    if is_valid_twilio_request(websocket, {}, settings):
        return True
    as_wss = "wss://" + settings.public_base_url.split("://", 1)[-1]
    wss_settings = settings.model_copy(update={"public_base_url": as_wss})
    return is_valid_twilio_request(websocket, {}, wss_settings)


@router.websocket(STREAM_PATH)
async def call_stream(websocket: WebSocket, call_id: str) -> None:
    settings = get_settings()
    line = LINES.get(call_id)
    if line is None or not _signed_stream(websocket, settings):
        logger.warning(
            "Refused media stream (call_id=%s, known=%s)", call_id, line is not None
        )
        await websocket.close(code=_POLICY_VIOLATION)
        return
    await websocket.accept()
    try:
        start = await read_twilio_start(websocket)
    except (TimeoutError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Media stream never started (call_id=%s): %s", call_id, exc)
        await websocket.close(code=_POLICY_VIOLATION)
        return
    except WebSocketDisconnect:
        logger.info("Media stream closed before it started (call_id=%s)", call_id)
        return
    await run_stream(websocket, start, line, settings)
