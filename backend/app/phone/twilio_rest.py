"""Thin async wrapper over the Twilio Voice REST calls the phone line makes.

The Twilio client blocks unless it's given an async HTTP client, so every call
here goes through its `*_async` methods on aiohttp, each with a timeout. Numbers
come in as arguments only from `TwilioTelephony`, which reads them from a
`NumberSource` (rule 2).
"""

from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.settings import Settings

TWILIO_TIMEOUT_S = 10.0
RING_TIMEOUT_S = 30
"""How long Twilio lets the agency's line ring before reporting `no-answer`."""
STATUS_EVENTS = ["initiated", "ringing", "answered", "completed"]

ENDED_STATUSES = frozenset({"completed", "busy", "failed", "no-answer", "canceled"})
"""Twilio call statuses after which the call is over."""


def stream_twiml(stream_url: str, *, play_digits: str | None = None) -> str:
    """TwiML that (optionally) presses keys, then streams the call to `stream_url`.

    `<Play digits>` sends real key presses (C37); "w" waits half a second first,
    so the line has stopped talking."""
    response = VoiceResponse()
    if play_digits:
        response.play(digits=play_digits)
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return str(response)


class TwilioCalls:
    """The `CallControl` the real line uses."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, http: AsyncTwilioHttpClient) -> Client:
        return Client(
            self._settings.twilio_account_sid,
            self._settings.twilio_auth_token,
            http_client=http,
        )

    async def create(self, *, to: str, twiml: str, status_callback: str) -> str:
        """Place the call from the agent's number; returns the call SID."""
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            call = await self._client(http).calls.create_async(
                to=to,
                from_=self._settings.twilio_agent_number,
                twiml=twiml,
                timeout=RING_TIMEOUT_S,
                status_callback=status_callback,
                status_callback_event=STATUS_EVENTS,
            )
        return call.sid

    async def update_twiml(self, sid: str, twiml: str) -> None:
        """Replace a live call's TwiML. This ends the stream it's running."""
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            await self._client(http).calls(sid).update_async(twiml=twiml)

    async def complete(self, sid: str) -> None:
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            await self._client(http).calls(sid).update_async(status="completed")

    async def status(self, sid: str) -> str:
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            call = await self._client(http).calls(sid).fetch_async()
        return call.status
