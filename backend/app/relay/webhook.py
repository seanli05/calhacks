"""Twilio WhatsApp webhook. For now it echoes text and acknowledges media."""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from twilio.twiml.messaging_response import MessagingResponse

from app.relay.inbound import InboundMessage
from app.relay.media import MediaDownloadError, download_media, get_media_client
from app.relay.signature import is_valid_twilio_request
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    media_client: Annotated[httpx.AsyncClient, Depends(get_media_client)],
) -> Response:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}

    if not is_valid_twilio_request(request, params, settings):
        logger.warning("Rejected /whatsapp request: bad Twilio signature")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        message = InboundMessage.model_validate(params)
    except ValidationError as exc:
        logger.warning(
            "Rejected /whatsapp request: malformed form (%d errors)", exc.error_count()
        )
        raise HTTPException(status_code=400, detail="Malformed Twilio request") from exc

    logger.info(
        "Inbound WhatsApp message sid=%s num_media=%d content_type=%s",
        message.message_sid,
        message.num_media,
        message.media_content_type,
    )
    reply = await _echo_reply(message, media_client, settings)
    return _twiml(reply)


async def _echo_reply(
    message: InboundMessage, media_client: httpx.AsyncClient, settings: Settings
) -> str:
    if message.num_media == 0 or not message.media_url:
        return f"Echo: {message.body}"

    content_type = message.media_content_type or "application/octet-stream"
    try:
        media = await download_media(
            media_client, message.media_url, content_type, message.message_sid, settings
        )
    except MediaDownloadError as exc:
        # No traceback: the chained httpx error would print the media URL.
        logger.error("%s", exc)
        return "Sorry, I couldn't download that. Please send it again."

    logger.info(
        "Downloaded media sid=%s bytes=%d", message.message_sid, len(media.data)
    )
    size_kb = max(1, round(len(media.data) / 1024))
    return f"Got your {media.content_type} ({size_kb} KB)"


def _twiml(text: str) -> Response:
    twiml = MessagingResponse()
    twiml.message(text)
    return Response(content=str(twiml), media_type="application/xml")
