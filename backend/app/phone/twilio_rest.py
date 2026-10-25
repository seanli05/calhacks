"""Thin async wrapper over the Twilio Voice REST calls the phone line makes.

The Twilio client blocks unless it's given an async HTTP client, so every call
here goes through its `*_async` methods on aiohttp, each with a timeout. Numbers
come in as arguments only from `TwilioTelephony`, which reads them from a
`NumberSource` (rule 2).
"""

from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Dial, Gather, Start, VoiceResponse

from app.phone.call_lines import JoinPrompt
from app.settings import Settings

TWILIO_TIMEOUT_S = 10.0
RING_TIMEOUT_S = 30
"""How long Twilio lets the agency's line ring before reporting `no-answer`."""
USER_RING_TIMEOUT_S = 15
"""How long the applicant's phone rings (the bridge, and listening in) before
`no-answer` (Plan.md C42). Short enough that Twilio gives up before most carriers'
voicemail answers (about 20-30 s), which matters with no join gate: voicemail that
picks up would be put through to the representative. A miss rings once more."""
GATE_TIMEOUT_S = 15
"""After the join prompt has played (twice), how long the applicant has to press a
key before the pickup counts as voicemail."""
STATUS_EVENTS = ["initiated", "ringing", "answered", "completed"]

ENDED_STATUSES = frozenset({"completed", "busy", "failed", "no-answer", "canceled"})
"""Twilio call statuses after which the call is over."""
NOT_ANSWERED_STATUSES = frozenset({"queued", "initiated", "ringing"})
"""Twilio cancels these with `canceled`; `completed` is only for answered calls."""


def hang_up_twiml() -> str:
    response = VoiceResponse()
    response.hangup()
    return str(response)


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


def user_gate_twiml(prompt: JoinPrompt, joined_url: str, missed_url: str) -> str:
    """Served when the applicant's phone picks up, which may be voicemail. Any key
    goes to `joined_url`; no key in time falls through to `missed_url`. Voicemail
    can't press a key, so the representative never hears it."""
    response = VoiceResponse()
    gather = Gather(num_digits=1, timeout=GATE_TIMEOUT_S, action=joined_url)
    gather.say(prompt.text, language=prompt.say_language, voice=prompt.voice, loop=2)
    response.append(gather)
    response.redirect(missed_url)
    return str(response)


def listen_stream_twiml(stream_url: str) -> str:
    """The listen leg after its key press: a media stream we only write to. Nothing
    the user says goes anywhere (`listen_audio.run_listener` ignores it)."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return str(response)


def conference_twiml(name: str, fork_url: str) -> str:
    """Puts a leg in the call's conference, with a listen-only fork of its own voice
    for the transcript. Each leg forks only its `inbound_track`, so each fork carries
    one speaker: Pipecat's serializer ignores the track field, and Twilio never opened
    a fork of the agency leg's `outbound_track` (spikes/bridge/README.md). No beep, no
    hold music while the other side joins, and either side leaving ends it. Nothing
    records (C29)."""
    response = VoiceResponse()
    start = Start()
    start.stream(url=fork_url, track="inbound_track")
    response.append(start)
    dial = Dial()
    dial.conference(
        name,
        beep=False,
        wait_url="",
        start_conference_on_enter=True,
        end_conference_on_exit=True,
    )
    response.append(dial)
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

    async def create(
        self,
        *,
        to: str,
        twiml: str,
        status_callback: str,
        ring_s: int = RING_TIMEOUT_S,
    ) -> str:
        """Place the call from the agent's number; returns the call SID. It rings
        for `ring_s`."""
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            call = await self._client(http).calls.create_async(
                to=to,
                from_=self._settings.twilio_agent_number,
                twiml=twiml,
                timeout=ring_s,
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

    async def end(self, sid: str) -> None:
        """End a call whether or not it was answered yet."""
        status = await self.status(sid)
        if status in ENDED_STATUSES:
            return
        ending = "canceled" if status in NOT_ANSWERED_STATUSES else "completed"
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            await self._client(http).calls(sid).update_async(status=ending)

    async def status(self, sid: str) -> str:
        async with AsyncTwilioHttpClient(timeout=TWILIO_TIMEOUT_S) as http:
            call = await self._client(http).calls(sid).fetch_async()
        return call.status
