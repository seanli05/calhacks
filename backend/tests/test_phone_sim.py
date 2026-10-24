"""The simulator's tree runtime, on a fake Claude and virtual time: trees route,
reprompt, give up, and end, so a simulator run fails only for the agent's reasons."""

import pytest
from app.contracts import CallOutcome
from app.phone.fakes import (
    FakeCallStore,
    FakeCaseReader,
    FakeClock,
    FakeEventLog,
    FakeNumberSource,
    FakeRelay,
    FakeTelephony,
    HungUp,
    PressedKeys,
    Said,
)
from app.phone.guard import GuardedTelephony
from app.phone.menu import MenuAction, PressAction, SayAction, WaitAction
from app.phone.ports import CallDeps
from app.phone.runner import run_call
from app.phone.sim_line import PhoneTree
from app.phone.sim_trees import SIM_BRIEF, TREES
from tests.test_phone_runner import FakeLlm, _job


async def _simulate(
    tree_name: str, menu: object
) -> tuple[PhoneTree, FakeTelephony, object]:
    clock = FakeClock()
    numbers = FakeNumberSource(
        verified={"case_123": "+18005550100"}, users={"user_9": "+15555550123"}
    )
    phone = PhoneTree(TREES[tree_name], clock)
    line = FakeTelephony(numbers, clock, responder=phone)
    phone.attach(line)
    deps = CallDeps(
        telephony=GuardedTelephony(line, []),
        relay=FakeRelay(clock),
        cases=FakeCaseReader({"brief_77": SIM_BRIEF}),
        calls=FakeCallStore(),
        events=FakeEventLog(),
        clock=clock,
    )
    llm = FakeLlm(menu, phase=_phase)
    report = await clock.run(run_call("job_12", _job(), deps, llm=llm))
    return phone, line, report


def _phase(heard: str) -> tuple[str, float]:
    text = heard.lower()
    if ("my name is" in text or "this is" in text) and "?" in text:
        return "human", 0.92
    if "hold" in text or "wait" in text or "caller number" in text:
        return "hold", 0.9
    return "menu", 0.9


def _wait(heard: str) -> MenuAction:
    return WaitAction(kind="wait", reason_en="t")


@pytest.mark.parametrize("name", sorted(TREES))
async def test_every_tree_ends_even_if_the_model_only_waits(name: str) -> None:
    """Some trees route on silence, and the decider's loop guard asks for a person,
    so the outcome varies; what matters is that every call ends with a report."""
    phone, line, report = await _simulate(name, _wait)
    assert report.outcome in set(CallOutcome)
    assert phone.visited
    assert isinstance(line.actions[-1], HungUp)


async def test_speech_tree_reaches_a_person() -> None:
    def menu(heard: str) -> MenuAction:
        text = heard.lower()
        if "for english, press 1" in text:
            return PressAction(
                kind="press", digits="1", option_label_en="English", reason_en="t"
            )
        if "briefly tell me" in text:
            return SayAction(
                kind="say", text="appointments and interviews", reason_en="t"
            )
        if "already scheduled, press 2" in text:
            return PressAction(
                kind="press", digits="2", option_label_en="interview", reason_en="t"
            )
        return WaitAction(kind="wait", reason_en="t")

    phone, line, report = await _simulate("speech_federal", menu)
    assert phone.visited == ["language", "reason", "appointments", "queue", "rep"]
    assert report.outcome == CallOutcome.PARTIAL
    assert Said("one") in line.actions


async def test_keypad_tree_is_deaf_to_speech() -> None:
    def menu(heard: str) -> MenuAction:
        if "appointments and interviews, press 5" in heard.lower():
            return PressAction(
                kind="press", digits="5", option_label_en="a", reason_en="t"
            )
        if "scheduled interview, press 1" in heard.lower():
            return PressAction(
                kind="press", digits="1", option_label_en="b", reason_en="t"
            )
        return WaitAction(kind="wait", reason_en="t")

    phone, line, report = await _simulate("keypad_state", menu)
    assert Said("five") in line.actions  # ignored by the tree
    assert PressedKeys("5") in line.actions and PressedKeys("1") in line.actions
    assert phone.visited[-2:] == ["queue", "rep"]
    assert report.outcome == CallOutcome.PARTIAL
