"""What the orchestrator may ask of a live call (person 4), when the user asks over
WhatsApp: to listen in ("sit in", "dial me in"), or to hang up ("hang up now").

In process, like `relay.ask_user` the other way: the backend is one process, and the
call's line lives in memory (`twilio_line.LINES`). Each request only asks the line,
which hands it to the call's runner as a line event, so the runner stays the one
place a call's state changes. No number passes through here: the runner rings the
user's own number (C6). The caller checks that the call is the user's
(`orchestrator/tools.py`).
"""

import logging

from app.contracts.common import CallId
from app.phone.listen_leg import ListenInResult
from app.phone.twilio_line import LINES, HangUpResult

logger = logging.getLogger(__name__)

__all__ = ["HangUpResult", "ListenInResult", "request_hang_up", "request_listen_in"]


def request_listen_in(call_id: CallId) -> ListenInResult:
    """Ring the user so they can hear the call, muted, until a person picks up; then
    they join it. `call_over` if this process has no live line for the call."""
    line = LINES.get(call_id)
    result: ListenInResult = "call_over" if line is None else line.request_listen_in()
    logger.info("listen-in requested (call_id=%s): %s", call_id, result)
    return result


def request_hang_up(call_id: CallId) -> HangUpResult:
    """End the call: every leg, the agency's included. If a representative is on and
    the user isn't yet, the agent tells them first. `call_over` if this process has
    no live line for the call."""
    line = LINES.get(call_id)
    result: HangUpResult = "call_over" if line is None else line.request_hang_up()
    logger.info("hang-up requested (call_id=%s): %s", call_id, result)
    return result
