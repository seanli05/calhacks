"""Thin async wrappers over the Twilio REST calls the spike makes."""

import asyncio

from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from spikes.dtmf.settings import SpikeSettings

TWILIO_TIMEOUT_S = 15.0


def stream_twiml(
    ws_url: str, *, mode: str, leg: str = "1", play_digits: str | None = None
) -> str:
    """TwiML that (optionally) plays digits, then streams the call to our /ws.

    `mode` and `leg` ride along as <Parameter>s so the server knows which test it's running.
    """
    response = VoiceResponse()
    if play_digits:
        response.play(digits=play_digits)
    connect = Connect()
    stream = connect.stream(url=ws_url)
    stream.parameter(name="mode", value=mode)
    stream.parameter(name="leg", value=leg)
    response.append(connect)
    return str(response)


async def place_call(settings: SpikeSettings, twiml: str) -> str:
    """Dial the mock agency from the agent number; returns the call SID."""
    async with AsyncTwilioHttpClient() as http:
        client = Client(
            settings.twilio_account_sid, settings.twilio_auth_token, http_client=http
        )
        call = await asyncio.wait_for(
            client.calls.create_async(
                to=settings.twilio_mock_agency_number,
                from_=settings.twilio_agent_number,
                twiml=twiml,
            ),
            TWILIO_TIMEOUT_S,
        )
    return call.sid


async def update_call(settings: SpikeSettings, call_sid: str, twiml: str) -> None:
    """Replace a live call's TwiML. This ends any <Stream> the call is running."""
    async with AsyncTwilioHttpClient() as http:
        client = Client(
            settings.twilio_account_sid, settings.twilio_auth_token, http_client=http
        )
        await asyncio.wait_for(
            client.calls(call_sid).update_async(twiml=twiml), TWILIO_TIMEOUT_S
        )
