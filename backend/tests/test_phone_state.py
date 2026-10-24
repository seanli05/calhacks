"""Call state machine: the demo path, every failure path, and illegal moves."""

import pytest
from app.contracts import CallOutcome, CallState
from app.phone.state import (
    TRANSITIONS,
    CallStateMachine,
    IllegalTransition,
    Transition,
    Trigger,
)

HAPPY_PATH = [
    Trigger.AGENCY_ANSWERED,
    Trigger.HOLD_STARTED,
    Trigger.HUMAN_DETECTED,
    Trigger.USER_DIALED,
    Trigger.USER_JOINED,
    Trigger.CALL_FINISHED,
    Trigger.REPORT_SAVED,
]


def run(*triggers: Trigger) -> CallStateMachine:
    machine = CallStateMachine()
    for trigger in triggers:
        machine.fire(trigger)
    return machine


def test_happy_path_reaches_ended_without_deciding_outcome() -> None:
    machine = CallStateMachine()
    states = [machine.fire(trigger).to_state for trigger in HAPPY_PATH]

    assert states == [
        CallState.MENU,
        CallState.HOLD,
        CallState.HUMAN_DETECTED,
        CallState.BRIDGING,
        CallState.CONNECTED,
        CallState.WRAP_UP,
        CallState.ENDED,
    ]
    assert machine.is_finished
    assert machine.outcome is None
    assert len(machine.history) == len(HAPPY_PATH)


@pytest.mark.parametrize(
    ("before_failure", "failure", "outcome"),
    [
        ([], Trigger.NO_ANSWER, CallOutcome.FAILED),
        (
            [Trigger.AGENCY_ANSWERED, Trigger.HOLD_STARTED],
            Trigger.HOLD_TIMEOUT,
            CallOutcome.FAILED,
        ),
        ([Trigger.AGENCY_ANSWERED], Trigger.AGENCY_HUNG_UP, CallOutcome.FAILED),
        (
            [Trigger.AGENCY_ANSWERED, Trigger.HOLD_STARTED],
            Trigger.AGENCY_HUNG_UP,
            CallOutcome.FAILED,
        ),
        (
            [Trigger.AGENCY_ANSWERED, Trigger.HOLD_STARTED, Trigger.HUMAN_DETECTED],
            Trigger.AGENCY_HUNG_UP,
            CallOutcome.FAILED,
        ),
        (
            [
                Trigger.AGENCY_ANSWERED,
                Trigger.HOLD_STARTED,
                Trigger.HUMAN_DETECTED,
                Trigger.USER_DIALED,
            ],
            Trigger.USER_UNREACHABLE,
            CallOutcome.USER_UNREACHABLE,
        ),
    ],
    ids=[
        "no_answer",
        "hold_timeout",
        "hangup_menu",
        "hangup_hold",
        "hangup_human",
        "user_unreachable",
    ],
)
def test_failures_go_through_wrap_up_and_keep_outcome(
    before_failure: list[Trigger], failure: Trigger, outcome: CallOutcome
) -> None:
    machine = run(*before_failure)

    assert machine.fire(failure).to_state == CallState.WRAP_UP
    assert machine.outcome == outcome

    machine.fire(Trigger.REPORT_SAVED)
    assert machine.is_finished
    assert machine.outcome == outcome, "a later step must not clear the outcome"


@pytest.mark.parametrize("steps_before_abort", range(5))
def test_agent_abort_before_user_joins_fails_through_wrap_up(
    steps_before_abort: int,
) -> None:
    """Covers dialing, menu, hold, human_detected, and bridging."""
    machine = run(*HAPPY_PATH[:steps_before_abort])

    assert machine.fire(Trigger.AGENT_ABORTED).to_state == CallState.WRAP_UP
    machine.fire(Trigger.REPORT_SAVED)
    assert machine.is_finished
    assert machine.outcome == CallOutcome.FAILED


def test_false_human_returns_to_hold_and_can_still_reach_a_human() -> None:
    machine = run(Trigger.AGENCY_ANSWERED, Trigger.HOLD_STARTED, Trigger.HUMAN_DETECTED)

    assert machine.fire(Trigger.FALSE_HUMAN).to_state == CallState.HOLD
    assert machine.fire(Trigger.HUMAN_DETECTED).to_state == CallState.HUMAN_DETECTED


def test_late_agency_hangup_during_wrap_up_keeps_outcome() -> None:
    machine = run(
        Trigger.AGENCY_ANSWERED,
        Trigger.HOLD_STARTED,
        Trigger.HUMAN_DETECTED,
        Trigger.USER_DIALED,
        Trigger.USER_UNREACHABLE,
        Trigger.AGENCY_HUNG_UP,
        Trigger.REPORT_SAVED,
    )

    assert machine.is_finished
    assert machine.outcome == CallOutcome.USER_UNREACHABLE


@pytest.mark.parametrize(
    ("before", "trigger"),
    [
        ([Trigger.AGENCY_ANSWERED], Trigger.USER_JOINED),
        ([], Trigger.HUMAN_DETECTED),
        (HAPPY_PATH, Trigger.AGENCY_HUNG_UP),
        (HAPPY_PATH, Trigger.REPORT_SAVED),
    ],
    ids=[
        "user_joined_in_menu",
        "human_while_dialing",
        "hangup_after_end",
        "report_after_end",
    ],
)
def test_illegal_transition_raises_and_leaves_state(
    before: list[Trigger], trigger: Trigger
) -> None:
    machine = run(*before)
    state = machine.state

    with pytest.raises(IllegalTransition, match=f"{trigger} in state {state}"):
        machine.fire(trigger)
    assert machine.state == state
    assert len(machine.history) == len(before)


@pytest.mark.parametrize("state", list(CallState))
def test_every_pair_is_in_the_table_or_raises(state: CallState) -> None:
    """A new state or trigger with no table rows fails here instead of mid-call."""
    for trigger in Trigger:
        machine = CallStateMachine()
        machine._state = state
        if (state, trigger) in TRANSITIONS:
            assert isinstance(machine.fire(trigger), Transition)
        else:
            with pytest.raises(IllegalTransition):
                machine.fire(trigger)


def test_every_non_terminal_state_can_leave_and_ended_cannot() -> None:
    exits = {from_state for from_state, _ in TRANSITIONS}
    assert exits == set(CallState) - {CallState.ENDED}


def test_only_wrap_up_leads_to_ended() -> None:
    into_ended = {
        from_state
        for (from_state, _), (to, _, _) in TRANSITIONS.items()
        if to == CallState.ENDED
    }
    assert into_ended == {CallState.WRAP_UP}
