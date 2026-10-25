"""The listen leg: the user sits in on the call before a representative answers.

The user asks over WhatsApp (`control.request_listen_in`), and the line rings
their own number (C6) on a call of its own. It has a join gate like the bridge's,
because carrier voicemail answers unpicked calls and would record the agency (C29).
A key press puts the leg on a media stream that only plays the call to them
(`listen_audio.py`).

It's a separate call from the agency leg, so the user hanging up ends only this
leg: the agent's call goes on, and they can ask again. If a person picks up while
they listen, `TwilioTelephony.ring_user` moves this leg into the conference
instead of ringing them a second time (`take_for_bridge`).

    none → requested → ringing → listening → none

A finished leg's SID is retired, so its late callbacks change nothing.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from aiohttp import ClientError
from twilio.base.exceptions import TwilioRestException

from app.contracts.common import CallId, LanguageCode
from app.phone.call_lines import listen_prompt
from app.phone.line import LineEvent, ListenEnded, ListenRequested, ListenStarted
from app.phone.listen_audio import ListenMixer, ListenSink
from app.phone.twilio_rest import (
    ENDED_STATUSES,
    hang_up_twiml,
    listen_stream_twiml,
    user_gate_twiml,
)
from app.phone.twilio_urls import LineUrls

if TYPE_CHECKING:
    from app.phone.twilio_line import CallControl

logger = logging.getLogger(__name__)

type ListenStage = Literal["none", "requested", "ringing", "listening"]
type ListenInResult = Literal[
    "ringing", "already_listening", "rep_on_line", "call_over"
]
"""What a request to sit in got: we're ringing them, they're already on (or being
rung), a person is on the line so the bridge will call them, or no call is live."""
type EndReason = Literal["hung_up", "busy", "no_answer", "failed", "no_key_press"]

_NOT_REACHED: dict[str, EndReason] = {
    "busy": "busy",
    "no-answer": "no_answer",
    "failed": "failed",
}
_REST_ERRORS = (TwilioRestException, ClientError, TimeoutError)


class ListenLeg:
    """One call's listen leg. `TwilioTelephony` owns it and routes its callbacks."""

    def __init__(
        self,
        calls: "CallControl",
        urls: LineUrls,
        emit: Callable[[LineEvent], None],
        *,
        language: LanguageCode,
    ) -> None:
        self._calls = calls
        self._urls = urls
        self._emit = emit
        self._language = language
        self.stage: ListenStage = "none"
        self.sid: str | None = None
        self._retired: set[str] = set()
        self._sink: ListenSink | None = None
        self.mixer = ListenMixer()

    def request(self) -> ListenInResult:
        if self.stage != "none":
            return "already_listening"
        self.stage = "requested"
        self._emit(ListenRequested())
        return "ringing"

    async def ring(self, call_id: CallId, number: str) -> None:
        """Place the leg. A failed REST call doesn't raise: it's `ListenEnded`."""
        if self.stage != "requested":
            logger.info(
                "listen ring skipped (call_id=%s stage=%s)", call_id, self.stage
            )
            return
        self.stage = "ringing"
        try:
            sid = await self._calls.create(
                to=number,
                twiml=user_gate_twiml(
                    listen_prompt(self._language),
                    self._urls.listen_joined(call_id),
                    self._urls.listen_missed(call_id),
                ),
                status_callback=self._urls.listen_status(call_id),
            )
        except _REST_ERRORS as exc:
            logger.warning(
                "ringing the listener failed (call_id=%s): %s",
                call_id,
                type(exc).__name__,
            )
            self.end("failed")
            return
        if self.stage == "none":
            # The call hung up while this was placed: nobody else will end it.
            self._retired.add(sid)
            await self._cancel(call_id, sid)
            return
        self.sid = self.sid or sid
        logger.info("rang the listener (call_id=%s sid=%s)", call_id, sid)

    async def _cancel(self, call_id: CallId, sid: str) -> None:
        try:
            await self._calls.end(sid)
        except _REST_ERRORS as exc:
            logger.warning(
                "ending the listener failed (call_id=%s): %s",
                call_id,
                type(exc).__name__,
            )

    def drop_request(self) -> None:
        """A request the line can't take any more (a person picked up first)."""
        if self.stage == "requested":
            self.stage = "none"

    def on_status(self, call_sid: str, status: str) -> None:
        if not self._matches(call_sid):
            return
        self.sid = self.sid or call_sid
        if self.stage == "ringing":
            if status in _NOT_REACHED or status == "canceled":
                self.end(_NOT_REACHED.get(status, "failed"))
            elif status == "completed":
                self.end("no_key_press")  # picked up, put down before a key
        elif self.stage == "listening" and status in ENDED_STATUSES:
            self.end("hung_up")

    def pressed_key(self, call_sid: str, call_id: CallId) -> str:
        if not self._matches(call_sid) or self.stage != "ringing":
            logger.info(
                "listen key press too late (call_id=%s stage=%s)", call_id, self.stage
            )
            return hang_up_twiml()
        self.sid = self.sid or call_sid
        self.stage = "listening"
        self._emit(ListenStarted())
        return listen_stream_twiml(self._urls.listen_stream(call_id))

    def missed_gate(self, call_sid: str) -> str:
        if self._matches(call_sid) and self.stage == "ringing":
            self.end("no_key_press")
        return hang_up_twiml()

    def attach(self, sink: ListenSink, call_sid: str) -> bool:
        if self.stage != "listening" or call_sid != self.sid:
            return False
        self._sink = sink
        self.mixer.attach(sink)
        return True

    def detach(self, sink: ListenSink) -> None:
        if self._sink is sink:
            self._sink = None
            self.mixer.detach(sink)

    def take_for_bridge(self) -> str | None:
        """The leg's SID, if the user is listening, handed over to the bridge: from
        now on it's the applicant's leg, and this one is back to `none`."""
        if self.stage != "listening" or self.sid is None:
            return None
        sid = self.sid
        self._finish()
        return sid

    def live_sid(self) -> str | None:
        """The SID of a leg still ringing or listening, to end with the call."""
        return self.sid if self.stage in ("ringing", "listening") else None

    def end(self, reason: EndReason) -> None:
        if self.stage == "none":
            return
        self._finish()
        self._emit(ListenEnded(reason=reason))

    def _finish(self) -> None:
        if self.sid is not None:
            self._retired.add(self.sid)
        self.sid = None
        self.stage = "none"
        if self._sink is not None:
            self.mixer.detach(self._sink)
            self._sink = None

    def _matches(self, call_sid: str) -> bool:
        if call_sid in self._retired or self.stage in ("none", "requested"):
            return False
        return self.sid is None or call_sid == self.sid
