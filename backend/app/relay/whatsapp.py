"""Thin wrapper over Twilio WhatsApp: send text and download media. Faked in tests."""

import asyncio
import logging
from functools import lru_cache
from typing import Protocol

import httpx
from twilio.base.exceptions import TwilioException, TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client

from app.relay.inbound import WHATSAPP_PREFIX, InboundMedia
from app.relay.media import DownloadedMedia, download_media
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Twilio rejects WhatsApp bodies over 1,600 characters.
MAX_BODY_CHARS = 1600
SEND_TIMEOUT_S = 10.0


class WhatsAppSendError(Exception):
    """Twilio didn't accept an outbound message."""


class WhatsApp(Protocol):
    async def send(self, to_number: str, body: str) -> list[str]:
        """Send `body` to an E.164 number; returns one Twilio SID per part sent."""
        ...

    async def download(
        self, media: InboundMedia, message_sid: str
    ) -> DownloadedMedia: ...


def split_body(body: str, limit: int = MAX_BODY_CHARS) -> list[str]:
    """Split a long message into parts of at most `limit` characters, preferring
    paragraph, then line, then word breaks."""
    parts: list[str] = []
    rest = body.strip()
    while len(rest) > limit:
        window = rest[: limit + 1]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


class TwilioWhatsApp:
    """Sends through the Twilio REST SDK (most messages aren't replies to a webhook,
    so TwiML can't carry them). The SDK is sync, so calls run in a worker thread."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._twilio = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            http_client=TwilioHttpClient(timeout=SEND_TIMEOUT_S),
        )

    def _send_part(self, to_number: str, body: str) -> str:
        message = self._twilio.messages.create(
            from_=self._settings.twilio_whatsapp_from,
            to=WHATSAPP_PREFIX + to_number,
            body=body,
        )
        return str(message.sid)

    async def send(self, to_number: str, body: str) -> list[str]:
        sids = []
        for part in split_body(body):
            try:
                sids.append(await asyncio.to_thread(self._send_part, to_number, part))
            except TwilioRestException as exc:
                # Code and status only: Twilio's message text can include numbers.
                raise WhatsAppSendError(
                    f"Twilio send failed after {len(sids)} parts: error {exc.code} "
                    f"(HTTP {exc.status}), see twilio.com/docs/errors/{exc.code}"
                ) from exc
            # requests' errors (timeouts, connection) subclass OSError.
            except (TwilioException, OSError) as exc:
                raise WhatsAppSendError(
                    f"Twilio send failed after {len(sids)} parts: {type(exc).__name__}"
                ) from exc
        return sids

    async def download(self, media: InboundMedia, message_sid: str) -> DownloadedMedia:
        async with httpx.AsyncClient() as client:
            return await download_media(
                client, media.url, media.content_type, message_sid, self._settings
            )


@lru_cache
def get_whatsapp() -> WhatsApp:
    return TwilioWhatsApp(get_settings())
