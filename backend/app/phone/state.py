"""Call state machine (Plan.md → Phone agent): which state changes are legal.

Pure and synchronous: no I/O, no clock. The call runner fires triggers here, then
persists the new state (`writes.phone.set_call_state`) and logs `event_type`.
Every path reaches `ended` through `wrap_up`, so a call report (P3) is always
written. ask_user and menu steps (key presses, speech) happen inside `menu` and
don't change state.

`call.dialing` is never a transition's `event_type`, because `dialing` is the
starting state. The runner must log it itself when it places the call; it's one
of the events that message the user (P2).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.contracts import CallOutcome, CallState, EventType


class Trigger(StrEnum):
    """Something that happened during a call. Not `Event`, which is the log contract."""

    AGENCY_ANSWERED = "agency_answered"
    NO_ANSWER = "no_answer"
    """Busy, no answer, or the call failed to connect."""
    MENU_RETURNED = "menu_returned"
    """An automated menu started again after hold (a transfer into another tree)."""
    HOLD_STARTED = "hold_started"
    HUMAN_DETECTED = "human_detected"
    """Fire only on a confident human reading (`phase.py`): entering `human_detected`
    messages the user "Someone picked up" (P2). Normally Claude's; if Claude is down,
    only on strong combined cues, so an outage on hold can't lose the call."""
    FALSE_HUMAN = "false_human"
    """Back to hold after a confirmed human, e.g. a rep who says "let me transfer you"."""
    USER_DIALED = "user_dialed"
    USER_JOINED = "user_joined"
    USER_UNREACHABLE = "user_unreachable"
    """The user didn't answer the bridged call within 30 s (Failure rules)."""
    HOLD_TIMEOUT = "hold_timeout"
    """Hold passed `max_hold_minutes`."""
    AGENCY_HUNG_UP = "agency_hung_up"
    AGENT_ABORTED = "agent_aborted"
    """Our side gives up before the user is on (crash, menu loop), so the report
    still gets written and the cause isn't blamed on the agency."""
    CALL_FINISHED = "call_finished"
    """The bridged conversation ended normally."""
    USER_ENDED = "user_ended"
    """The user asked over WhatsApp to end the call (`control.request_hang_up`).
    Before they're on it, the call is `cancelled`; once they are, the report
    reads the conversation like any other."""
    REPORT_SAVED = "report_saved"


type _Rule = tuple[CallState, CallOutcome | None, EventType | None]

S = CallState
T = Trigger
FAILED = CallOutcome.FAILED
CANCELLED = CallOutcome.CANCELLED

TRANSITIONS: dict[tuple[CallState, Trigger], _Rule] = {
    # (from, trigger):                  (to, outcome, event to log)
    (S.DIALING, T.AGENCY_ANSWERED): (S.MENU, None, None),
    (S.DIALING, T.NO_ANSWER): (S.WRAP_UP, FAILED, None),
    (S.MENU, T.HOLD_STARTED): (S.HOLD, None, EventType.CALL_ON_HOLD),
    (S.MENU, T.HUMAN_DETECTED): (S.HUMAN_DETECTED, None, EventType.CALL_HUMAN_DETECTED),
    (S.MENU, T.AGENCY_HUNG_UP): (S.WRAP_UP, FAILED, None),
    # Real USCIS lines sometimes transfer from hold into another automated menu.
    # Raising there would crash a live call, so returning to menu is legal.
    (S.HOLD, T.MENU_RETURNED): (S.MENU, None, None),
    (S.HOLD, T.HUMAN_DETECTED): (S.HUMAN_DETECTED, None, EventType.CALL_HUMAN_DETECTED),
    (S.HOLD, T.HOLD_TIMEOUT): (S.WRAP_UP, FAILED, None),
    (S.HOLD, T.AGENCY_HUNG_UP): (S.WRAP_UP, FAILED, None),
    (S.HUMAN_DETECTED, T.FALSE_HUMAN): (S.HOLD, None, EventType.CALL_ON_HOLD),
    (S.HUMAN_DETECTED, T.USER_DIALED): (S.BRIDGING, None, EventType.CALL_USER_DIALED),
    (S.HUMAN_DETECTED, T.AGENCY_HUNG_UP): (S.WRAP_UP, FAILED, None),
    (S.BRIDGING, T.USER_JOINED): (S.CONNECTED, None, EventType.CALL_USER_JOINED),
    (S.BRIDGING, T.USER_UNREACHABLE): (
        S.WRAP_UP,
        CallOutcome.USER_UNREACHABLE,
        EventType.CALL_USER_UNREACHABLE,
    ),
    (S.BRIDGING, T.AGENCY_HUNG_UP): (S.WRAP_UP, FAILED, None),
    (S.DIALING, T.AGENT_ABORTED): (S.WRAP_UP, FAILED, None),
    (S.MENU, T.AGENT_ABORTED): (S.WRAP_UP, FAILED, None),
    (S.HOLD, T.AGENT_ABORTED): (S.WRAP_UP, FAILED, None),
    (S.HUMAN_DETECTED, T.AGENT_ABORTED): (S.WRAP_UP, FAILED, None),
    (S.BRIDGING, T.AGENT_ABORTED): (S.WRAP_UP, FAILED, None),
    (S.DIALING, T.USER_ENDED): (S.WRAP_UP, CANCELLED, None),
    (S.MENU, T.USER_ENDED): (S.WRAP_UP, CANCELLED, None),
    (S.HOLD, T.USER_ENDED): (S.WRAP_UP, CANCELLED, None),
    (S.HUMAN_DETECTED, T.USER_ENDED): (S.WRAP_UP, CANCELLED, None),
    (S.BRIDGING, T.USER_ENDED): (S.WRAP_UP, CANCELLED, None),
    (S.CONNECTED, T.USER_ENDED): (S.WRAP_UP, None, None),
    # Once the user is on, resolved vs. partial is the call report's call.
    (S.CONNECTED, T.CALL_FINISHED): (S.WRAP_UP, None, None),
    (S.CONNECTED, T.AGENCY_HUNG_UP): (S.WRAP_UP, None, None),
    # The agency leg drops while we wrap up (e.g. after "they'll call back");
    # recorded so a late hang-up callback doesn't crash report writing.
    (S.WRAP_UP, T.AGENCY_HUNG_UP): (S.WRAP_UP, None, None),
    (S.WRAP_UP, T.REPORT_SAVED): (S.ENDED, None, EventType.CALL_ENDED),
}


class IllegalTransition(ValueError):
    def __init__(self, state: CallState, trigger: Trigger) -> None:
        super().__init__(f"illegal call transition: {trigger} in state {state}")
        self.state = state
        self.trigger = trigger


class Transition(BaseModel):
    """One step of a call; `outcome` is only what this trigger decided on its own."""

    model_config = ConfigDict(frozen=True)

    from_state: CallState
    to_state: CallState
    trigger: Trigger
    outcome: CallOutcome | None
    event_type: EventType | None


class CallStateMachine:
    """One call's state. Starts in `dialing`; `ended` is terminal."""

    def __init__(self) -> None:
        self._state = CallState.DIALING
        self._outcome: CallOutcome | None = None
        self.history: list[Transition] = []

    @property
    def state(self) -> CallState:
        return self._state

    @property
    def outcome(self) -> CallOutcome | None:
        """Sticky: once a trigger sets it, later steps don't clear it."""
        return self._outcome

    @property
    def is_finished(self) -> bool:
        return self._state == CallState.ENDED

    def fire(self, trigger: Trigger) -> Transition:
        rule = TRANSITIONS.get((self._state, trigger))
        if rule is None:
            raise IllegalTransition(self._state, trigger)
        to_state, outcome, event_type = rule
        transition = Transition(
            from_state=self._state,
            to_state=to_state,
            trigger=trigger,
            outcome=outcome,
            event_type=event_type,
        )
        self._state = to_state
        if outcome is not None:
            self._outcome = outcome
        self.history.append(transition)
        return transition
