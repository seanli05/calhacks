"""Thin wrapper over Twilio WhatsApp: send text, download media, and show "typing…".
Faked in tests."""

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
# Twilio's typing indicator (WhatsApp, public beta). Not in the Python SDK yet.
TYPING_URL = "https://messaging.twilio.com/v3/Indicators/Typing.json"
TYPING_TIMEOUT_S = 5.0


class WhatsAppSendError(Exception):
    """Twilio didn't accept an outbound message."""


class WhatsApp(Protocol):
    async def send(self, to_number: str, body: str) -> list[str]:
        """Send `body` to an E.164 number; returns one Twilio SID per part sent."""
        ...

    async def download(
        self, media: InboundMedia, message_sid: str
    ) -> DownloadedMedia: ...

    async def typing(self, message_sid: str) -> None:
        """Show "typing…" in reply to an inbound message, and mark it read. WhatsApp
        clears it when our next message arrives, or after 25 s. Best effort: never
        raises."""
        ...


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
        self._typing_failed = False
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

    async def typing(self, message_sid: str) -> None:
        settings = self._settings
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            return
        try:
            async with httpx.AsyncClient(timeout=TYPING_TIMEOUT_S) as client:
                response = await client.post(
                    TYPING_URL,
                    json={"channel": "WHATSAPP", "messageId": message_sid},
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The status only: the response body can echo the message's details.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Warn once; a sandbox without the beta would fail on every message.
            log = logger.debug if self._typing_failed else logger.warning
            log(
                "Typing indicator failed sid=%s: %s %s",
                message_sid,
                type(exc).__name__,
                status or "",
            )
            self._typing_failed = True


@lru_cache
def get_whatsapp() -> WhatsApp:
    return TwilioWhatsApp(get_settings())
