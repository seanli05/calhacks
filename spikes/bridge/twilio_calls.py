"""TwiML builders and thin async wrappers over the Twilio REST calls the spike makes."""

import asyncio

from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Dial, Gather, Start, VoiceResponse

from spikes.bridge.settings import BridgeSpikeSettings, http_url, ws_url

TWILIO_TIMEOUT_S = 15.0
# Plan.md failure rules: the user gets 30 s to answer the bridged call.
USER_RING_TIMEOUT_S = 30
# After pickup, how long the user has to press a key once the prompt finishes.
GATE_TIMEOUT_S = 15
GATE_PROMPT = "Your call with the immigration office is ready. Press 1 to join."


def conference_name(agency_sid: str) -> str:
    return f"bridge-{agency_sid}"


def agency_stream_twiml(settings: BridgeSpikeSettings) -> str:
    """Before the bridge: the agency leg on our two-way media stream."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url(settings, "/ws")).parameter(name="leg", value="pre")
    response.append(connect)
    return str(response)


def _dial_conference(settings: BridgeSpikeSettings, agency_sid: str) -> Dial:
    # No beep, no hold music while the other side joins, and either side leaving ends it.
    dial = Dial()
    dial.conference(
        conference_name(agency_sid),
        beep=False,
        wait_url="",
        start_conference_on_enter=True,
        end_conference_on_exit=True,
        status_callback=http_url(settings, "/status/conference"),
        status_callback_event="start end join leave",
    )
    return dial


def _fork_inbound(settings: BridgeSpikeSettings, speaker: str) -> Start:
    """Fork this leg's own voice to STT.

    Each leg forks only its inbound track, so each stream carries one speaker.
    Pipecat's Twilio serializer ignores the track field, so `both_tracks` would mix
    them. Take 1 forked the user from the agency leg's `outbound_track`, and Twilio
    never opened that stream.
    """
    start = Start()
    stream = start.stream(url=ws_url(settings, "/ws-fork"), track="inbound_track")
    stream.parameter(name="speaker", value=speaker)
    return start


def user_gate_twiml(settings: BridgeSpikeSettings) -> str:
    """Served on pickup: ask for a key press before bridging.

    Twilio reports voicemail picking up as an answered call, so pickup alone can't
    tell us the user is there. Voicemail can't press a key. No key in time falls
    through to /twiml/user/missed.
    """
    response = VoiceResponse()
    gather = Gather(
        num_digits=1,
        timeout=GATE_TIMEOUT_S,
        action=http_url(settings, "/twiml/user/joined"),
    )
    gather.say(GATE_PROMPT, loop=2)
    response.append(gather)
    response.redirect(http_url(settings, "/twiml/user/missed"))
    return str(response)


def user_conference_twiml(settings: BridgeSpikeSettings, agency_sid: str) -> str:
    """Served once the user presses a key: fork their voice, then join the conference."""
    response = VoiceResponse()
    response.append(_fork_inbound(settings, "user"))
    response.append(_dial_conference(settings, agency_sid))
    return str(response)


def agency_conference_twiml(settings: BridgeSpikeSettings, agency_sid: str) -> str:
    """After the bridge: fork the agency's voice, then join the conference."""
    response = VoiceResponse()
    response.append(_fork_inbound(settings, "agency"))
    response.append(_dial_conference(settings, agency_sid))
    return str(response)


def _client(settings: BridgeSpikeSettings, http: AsyncTwilioHttpClient) -> Client:
    return Client(
        settings.twilio_account_sid, settings.twilio_auth_token, http_client=http
    )


async def dial_agency(settings: BridgeSpikeSettings, to: str) -> str:
    """Dial the agency leg from the agent number; returns the call SID."""
    async with AsyncTwilioHttpClient() as http:
        call = await asyncio.wait_for(
            _client(settings, http).calls.create_async(
                to=to,
                from_=settings.twilio_agent_number,
                twiml=agency_stream_twiml(settings),
            ),
            TWILIO_TIMEOUT_S,
        )
    return call.sid


async def ring_user(settings: BridgeSpikeSettings) -> str:
    """Ring the user's phone; Twilio fetches /twiml/user when they answer."""
    async with AsyncTwilioHttpClient() as http:
        call = await asyncio.wait_for(
            _client(settings, http).calls.create_async(
                to=settings.bridge_spike_user_number,
                from_=settings.twilio_agent_number,
                url=http_url(settings, "/twiml/user"),
                timeout=USER_RING_TIMEOUT_S,
                status_callback=http_url(settings, "/status/user"),
                status_callback_event=["initiated", "ringing", "answered", "completed"],
            ),
            TWILIO_TIMEOUT_S,
        )
    return call.sid


async def update_call(settings: BridgeSpikeSettings, call_sid: str, twiml: str) -> None:
    """Replace a live call's TwiML. This ends any <Connect><Stream> the call is running."""
    async with AsyncTwilioHttpClient() as http:
        await asyncio.wait_for(
            _client(settings, http).calls(call_sid).update_async(twiml=twiml),
            TWILIO_TIMEOUT_S,
        )


async def hang_up(settings: BridgeSpikeSettings, call_sid: str) -> None:
    async with AsyncTwilioHttpClient() as http:
        await asyncio.wait_for(
            _client(settings, http).calls(call_sid).update_async(status="completed"),
            TWILIO_TIMEOUT_S,
        )
