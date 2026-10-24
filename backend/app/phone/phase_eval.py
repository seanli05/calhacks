"""Manual eval of the line-phase classifier against real Claude. Costs a little; not a test.

    python -m app.phone.phase_eval           # from backend/, needs ANTHROPIC_API_KEY

Cases are written from how US agency and large-company lines generally behave, not
from any one line (CLAUDE.md → the mock agency is a test target). Each case checks
the phase and the trigger it fires, never wording. The tests reuse `CASES` to check
the fallback path never fires a wrong trigger.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.contracts import CallState
from app.phone.llm import AnthropicLlmClient
from app.phone.phase import HeardTurn, Phase, ReadingSource, classify, to_trigger
from app.phone.state import Trigger

M, H, U, X = Phase.MENU, Phase.HOLD, Phase.HUMAN, Phase.UNCLEAR


@dataclass
class Case:
    name: str
    state: CallState
    heard: str
    phases: frozenset[Phase]
    """Any of these is a correct reading."""
    trigger: Trigger | None
    """The trigger a correct, confident reading fires."""
    history: list[HeardTurn] = field(default_factory=list)
    at_s: float = 600.0
    state_since_s: float = 120.0


def heard(text: str, at_s: float, phase: Phase) -> HeardTurn:
    return HeardTurn(text=text, at_s=at_s, phase=phase)


HOLD_IMPORTANT = (
    "Your call is important to us. Please continue to hold and the next available "
    "representative will be with you shortly."
)
HOLD_BUSY = (
    "Thank you for holding. All of our representatives are still assisting other "
    "callers. Please stay on the line and your call will be answered in the order it "
    "was received."
)
HOLD_WEB = (
    "Did you know you can check your case status and find answers to common questions "
    "on our website, any time, day or night?"
)
HOLD_LOOP = [
    heard(HOLD_IMPORTANT, 420, H),
    heard(HOLD_WEB, 470, H),
    heard(HOLD_BUSY, 530, H),
]

CASES = [
    Case(
        "IVR greeting with language option",
        CallState.MENU,
        "Thank you for calling. This call may be monitored or recorded. Para español, "
        "oprima dos.",
        frozenset({M}),
        None,
        at_s=5,
        state_since_s=0,
    ),
    Case(
        "transfer to the queue",
        CallState.MENU,
        "Okay. Please hold while I transfer your call to the next available "
        "representative.",
        frozenset({H}),
        Trigger.HOLD_STARTED,
        history=[heard("Please tell me briefly the reason for your call.", 70, M)],
        at_s=80,
        state_since_s=0,
    ),
    Case(
        "wait-time announcement",
        CallState.MENU,
        "Your estimated wait time is more than forty-five minutes. Please stay on the "
        "line.",
        frozenset({H}),
        Trigger.HOLD_STARTED,
        at_s=90,
        state_since_s=0,
    ),
    Case(
        "virtual assistant with a name",
        CallState.MENU,
        "Hi, I'm Ava, the automated virtual assistant. In a few words, what can I help "
        "you with today?",
        frozenset({M}),
        None,
        at_s=20,
        state_since_s=0,
    ),
    Case(
        "person answers straight from a menu",
        CallState.MENU,
        "Good afternoon, asylum office, this is Kevin speaking, how can I help you?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=[heard("For all other questions, press zero.", 30, M)],
        at_s=45,
        state_since_s=0,
    ),
    Case(
        "hold, call is important",
        CallState.HOLD,
        HOLD_IMPORTANT,
        frozenset({H}),
        None,
        at_s=150,
    ),
    Case(
        "hold, rhetorical question",
        CallState.HOLD,
        HOLD_WEB,
        frozenset({H}),
        None,
        history=[heard(HOLD_IMPORTANT, 150, H)],
        at_s=200,
    ),
    Case(
        "hold, fraud notice",
        CallState.HOLD,
        "Please be aware that this agency will never call you to demand payment over "
        "the phone. If you receive a call like that, hang up.",
        frozenset({H}),
        None,
        history=HOLD_LOOP,
    ),
    Case(
        "hold, loop repeats garbled",
        CallState.HOLD,
        "your call is important to us please continue to hold and the next available "
        "representative will be with you shortly",
        frozenset({H}),
        None,
        history=HOLD_LOOP,
    ),
    Case(
        "hold, garbled announcement",
        CallState.HOLD,
        "your call is in port and to us please stay on the lie and you're called will "
        "be answered in the order received",
        frozenset({H}),
        None,
        history=HOLD_LOOP,
    ),
    Case(
        "rep opens like the hold message",
        CallState.HOLD,
        "Thank you for holding, my name is Daniel. Can I get the name of the person I'm "
        "speaking with?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=HOLD_LOOP,
    ),
    Case(
        "rep, terse",
        CallState.HOLD,
        "Immigration services, this is Ms. Patel, how can I help you?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=HOLD_LOOP,
    ),
    Case(
        "rep with an ID, no name cue",
        CallState.HOLD,
        "Thanks for waiting. You've reached officer Ramirez, ID four seven two. What's "
        "the reason for your call today?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=HOLD_LOOP,
    ),
    Case(
        "recording then person in one utterance",
        CallState.HOLD,
        "This call may be monitored or recorded for quality assurance. Hi, this is Jen, "
        "who do I have the pleasure of speaking with?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=HOLD_LOOP,
    ),
    Case(
        "rep says hello into silence",
        CallState.HOLD,
        "Hello? Hello, is anybody on the line?",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=[*HOLD_LOOP, heard("Hello?", 596, X)],
    ),
    Case(
        "garbled rep greeting",
        CallState.HOLD,
        "thank you for hold in this is uh sarah with the uh contact center how may i help",
        frozenset({U}),
        Trigger.HUMAN_DETECTED,
        history=HOLD_LOOP,
    ),
    Case(
        "menu after a transfer",
        CallState.HOLD,
        "You've reached the case information line. For questions about an interview or "
        "an appointment, press one. For all other inquiries, press two.",
        frozenset({M}),
        Trigger.MENU_RETURNED,
        history=HOLD_LOOP,
    ),
    Case(
        "speech menu after a transfer",
        CallState.HOLD,
        "Welcome to the interview scheduling unit. Please tell me briefly, are you "
        "calling to reschedule, or to confirm an appointment?",
        frozenset({M}),
        Trigger.MENU_RETURNED,
        history=HOLD_LOOP,
    ),
    Case(
        "callback offer during hold",
        CallState.HOLD,
        "We are experiencing high call volumes. To receive a callback when an agent is "
        "available, press one. To keep holding, stay on the line.",
        frozenset({M, H}),
        Trigger.MENU_RETURNED,
        history=HOLD_LOOP,
    ),
    # Flaky: Claude reads this as hold or human run to run (phase.py → Known gaps).
    Case(
        "rep transfers the caller",
        CallState.HUMAN_DETECTED,
        "Okay, that's handled by a different department. Let me transfer you, please "
        "hold.",
        frozenset({H}),
        Trigger.FALSE_HUMAN,
        history=[
            *HOLD_LOOP,
            heard("Thanks for holding, this is Mark, who am I speaking with?", 580, U),
        ],
        state_since_s=580,
    ),
    Case(
        "hold loop resumes after a false human",
        CallState.HUMAN_DETECTED,
        HOLD_BUSY,
        frozenset({H}),
        Trigger.FALSE_HUMAN,
        history=[*HOLD_LOOP, heard("Thank you for your patience.", 575, U)],
        state_since_s=575,
    ),
    Case(
        "rep keeps talking while the user joins",
        CallState.HUMAN_DETECTED,
        "Sure, no problem. I'll pull up the system while they're joining.",
        # Unclear is fine: it fires nothing here, and the model can't see our intro.
        frozenset({U, X}),
        None,
        history=[
            *HOLD_LOOP,
            heard("This is Ana, how can I help you today?", 580, U),
        ],
        state_since_s=580,
    ),
]


async def run() -> int:
    client = AnthropicLlmClient()
    passed = 0
    latencies: list[float] = []
    print(f"{'case':42} {'ok':4} {'ms':>6} {'src':8} {'phase':8} {'conf':>4}  trigger")
    for case in CASES:
        start = time.perf_counter()
        reading = await classify(
            case.heard,
            at_s=case.at_s,
            state=case.state,
            history=case.history,
            state_since_s=case.state_since_s,
            client=client,
        )
        ms = (time.perf_counter() - start) * 1000
        if reading.source == ReadingSource.MODEL:
            latencies.append(ms)
        trigger = to_trigger(case.state, reading)
        ok = (
            reading.phase in case.phases
            and trigger == case.trigger
            and reading.source != ReadingSource.FALLBACK
        )
        passed += ok
        print(
            f"{case.name:42} {'PASS' if ok else 'FAIL':4} {ms:6.0f} {reading.source:8} "
            f"{reading.phase:8} {reading.confidence:4.2f}  "
            f"{trigger or '-'} (want {case.trigger or '-'})"
        )
        print(f"{'':45}why: {reading.reason_en}")
    latencies.sort()
    if latencies:
        p50 = latencies[len(latencies) // 2]
        print(
            f"\n{passed}/{len(CASES)} passed; model calls: p50 {p50:.0f} ms, "
            f"max {latencies[-1]:.0f} ms"
        )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    raise SystemExit(asyncio.run(run()))
