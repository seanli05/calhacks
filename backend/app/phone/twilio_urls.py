"""Where Twilio reaches one call's line: the paths `routes.py` serves, and their
full URLs from `PUBLIC_BASE_URL`, which `TwilioTelephony` hands to Twilio."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.contracts.common import CallId
from app.settings import Settings

STATUS_PATH = "/phone/calls/{call_id}/status"
STREAM_PATH = "/phone/calls/{call_id}/stream"
USER_STATUS_PATH = "/phone/calls/{call_id}/user/status"
USER_JOINED_PATH = "/phone/calls/{call_id}/user/joined"
USER_MISSED_PATH = "/phone/calls/{call_id}/user/missed"
FORK_PATH = "/phone/calls/{call_id}/fork/{speaker}"
LISTEN_STATUS_PATH = "/phone/calls/{call_id}/listen/status"
LISTEN_JOINED_PATH = "/phone/calls/{call_id}/listen/joined"
LISTEN_MISSED_PATH = "/phone/calls/{call_id}/listen/missed"
LISTEN_STREAM_PATH = "/phone/calls/{call_id}/listen/stream"

type Speaker = Literal["agency", "user"]


@dataclass(frozen=True)
class LineUrls:
    """Where Twilio reaches us for one call, from `PUBLIC_BASE_URL`."""

    base_url: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "LineUrls":
        if not settings.public_base_url:
            raise ValueError("PUBLIC_BASE_URL is not set; Twilio can't reach us")
        return cls(settings.public_base_url.rstrip("/"))

    def status(self, call_id: CallId) -> str:
        return self.base_url + STATUS_PATH.format(call_id=call_id)

    def stream(self, call_id: CallId) -> str:
        return self._wss() + STREAM_PATH.format(call_id=call_id)

    def user_status(self, call_id: CallId) -> str:
        return self.base_url + USER_STATUS_PATH.format(call_id=call_id)

    def user_joined(self, call_id: CallId) -> str:
        return self.base_url + USER_JOINED_PATH.format(call_id=call_id)

    def user_missed(self, call_id: CallId) -> str:
        return self.base_url + USER_MISSED_PATH.format(call_id=call_id)

    def fork(self, call_id: CallId, speaker: Speaker) -> str:
        return self._wss() + FORK_PATH.format(call_id=call_id, speaker=speaker)

    def listen_status(self, call_id: CallId) -> str:
        return self.base_url + LISTEN_STATUS_PATH.format(call_id=call_id)

    def listen_joined(self, call_id: CallId) -> str:
        return self.base_url + LISTEN_JOINED_PATH.format(call_id=call_id)

    def listen_missed(self, call_id: CallId) -> str:
        return self.base_url + LISTEN_MISSED_PATH.format(call_id=call_id)

    def listen_stream(self, call_id: CallId) -> str:
        return self._wss() + LISTEN_STREAM_PATH.format(call_id=call_id)

    def _wss(self) -> str:
        return f"wss://{urlsplit(self.base_url).netloc}"
