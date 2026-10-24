"""Twilio WhatsApp webhook. It verifies and parses the message, hands it to the pipe
as a background task, and returns empty TwiML at once; replies go out through the
REST API."""

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import ValidationError
from twilio.twiml.messaging_response import MessagingResponse

from app.orchestrator.pipe import InboundPipe, get_pipe
from app.relay.inbound import InboundMessage
from app.relay.signature import is_valid_twilio_request
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    pipe: Annotated[InboundPipe, Depends(get_pipe)],
) -> Response:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}

    if not is_valid_twilio_request(request, params, settings):
        logger.warning("Rejected /whatsapp request: bad Twilio signature")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        message = InboundMessage.from_form(params)
    except ValidationError as exc:
        logger.warning(
            "Rejected /whatsapp request: malformed form (%d errors)", exc.error_count()
        )
        raise HTTPException(status_code=400, detail="Malformed Twilio request") from exc

    logger.info(
        "Inbound WhatsApp message sid=%s media=%s",
        message.message_sid,
        [item.content_type for item in message.media],
    )
    background_tasks.add_task(pipe.handle, message)
    return Response(content=str(MessagingResponse()), media_type="application/xml")
