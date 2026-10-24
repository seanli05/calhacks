"""Manual eval of the call report against real Claude. Costs a little; not a test.

    python -m app.phone.report_eval          # from backend/, needs ANTHROPIC_API_KEY

Transcripts are made up from how agency representatives generally talk, not from
any one line (CLAUDE.md → the mock agency is a test target). Each check asserts
properties of the report, never exact wording. The identifiers below are fake.
"""

import asyncio
import datetime as dt
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.contracts import CallOutcome, CallReport
from app.phone.ports import TranscriptLine
from app.phone.report import LlmReportBuilder, ReportInput
from app.phone.report_llm import AnthropicReportClient
from app.phone.state import Trigger

START = dt.datetime(2026, 10, 25, 17, 0, tzinfo=dt.UTC)
RECEIPT = "ZLA0987654321"
A_NUMBER = "A098765432"
DATE_OF_BIRTH = "1988-07-04"
BLOCKED = [RECEIPT, A_NUMBER, DATE_OF_BIRTH]

BRIEF = {
    "brief_id": "brief_eval",
    "case_id": "case_eval",
    "call_goal_en": (
        "Confirm the asylum interview is still scheduled; ask what to do if the "
        "interpreter can't come"
    ),
    "appointment": {
        "date": "2026-11-18",
        "time": "09:30",
        "location_ref": "<ref:interview_location>",
        "citation": "p1",
    },
    "questions_to_ask": [
        "Is the interview still scheduled?",
        "What should the applicant do if the interpreter can't come?",
    ],
}

type Check = Callable[[CallReport], bool]

INTRO = (
    "Hi, I'm an automated assistant calling on behalf of the applicant. I'm "
    "connecting them to this call now; please hold one moment."
)


@dataclass
class Case:
    name: str
    lines: list[tuple[int, str, str]]
    check: Check
    expect: str


def outcome_in(*outcomes: CallOutcome) -> Check:
    return lambda r: r.outcome in outcomes


def ref_is(value: str | None) -> Check:
    if value is None:
        return lambda r: r.reference_number is None
    digits = re.sub(r"\D", "", value)
    return lambda r: (
        r.reference_number is not None
        and re.sub(r"\D", "", r.reference_number) == digits
    )


def rep_is(name: str | None) -> Check:
    if name is None:
        return lambda r: r.rep_name is None
    return lambda r: r.rep_name is not None and name.lower() in r.rep_name.lower()


def deadline(date: str) -> Check:
    return lambda r: dt.date.fromisoformat(date) in r.new_deadlines


def no_deadlines(r: CallReport) -> bool:
    return not r.new_deadlines


def followup(r: CallReport) -> bool:
    return r.followup_needed


def steps_mention(pattern: str) -> Check:
    return lambda r: any(re.search(pattern, s, re.IGNORECASE) for s in r.next_steps_en)


def facts_mention(pattern: str) -> Check:
    return lambda r: any(
        re.search(pattern, f.fact, re.IGNORECASE) for f in r.proposed_facts
    )


def nothing_matches(pattern: str) -> Check:
    def check(r: CallReport) -> bool:
        texts = [*r.next_steps_en, *(f.fact for f in r.proposed_facts)]
        return not any(re.search(pattern, t, re.IGNORECASE) for t in texts)

    return check


def few_facts(r: CallReport) -> bool:
    return len(r.proposed_facts) <= 1


def all_of(*checks: Check) -> Check:
    return lambda r: all(check(r) for check in checks)


def no_identifiers(r: CallReport) -> bool:
    flat = re.sub(r"[^a-z0-9]", "", r.model_dump_json().lower())
    return not any(re.sub(r"[^a-z0-9]", "", v.lower()) in flat for v in BLOCKED)


def _hold(start: int, count: int, gap: int = 45) -> list[tuple[int, str, str]]:
    return [
        (
            start + gap * i,
            "agency",
            "All representatives are busy. Please stay on the line.",
        )
        for i in range(count)
    ]


MENU_PART = [
    (0, "agency", "Thank you for calling. Calls may be recorded."),
    (6, "agency", "For questions about an interview or appointment, press three."),
    (12, "agent", "three"),
    *_hold(20, 6),
]

CASES = [
    Case(
        "confirmed, ref and name",
        [
            *MENU_PART,
            (300, "agency", "Good afternoon, my name is Denise. How can I help?"),
            (304, "agent", INTRO),
            (330, "agency", "Okay ma'am, I'm looking at the interview now."),
            (
                360,
                "agency",
                (
                    "Yes, it's still on the calendar for November eighteenth at nine "
                    "thirty."
                ),
            ),
            (
                390,
                "agency",
                (
                    "If your interpreter can't make it, contact the asylum office before "
                    "the date and ask to reschedule. Don't just not show up."
                ),
            ),
            (
                420,
                "agency",
                "I'll give you a reference for today's call: S R 3 3 9 1 0.",
            ),
            (440, "agency", "Anything else I can help with? All right, take care."),
        ],
        all_of(
            outcome_in(CallOutcome.RESOLVED, CallOutcome.PARTIAL),
            ref_is("SR33910"),
            rep_is("Denise"),
            no_deadlines,
            steps_mention("reschedul|interpreter"),
        ),
        "resolved/partial, SR33910, Denise",
    ),
    Case(
        "no reference, can't help",
        [
            *MENU_PART,
            (300, "agency", "Contact center, how can I help you?"),
            (304, "agent", INTRO),
            (
                340,
                "agency",
                (
                    "We don't have access to asylum office calendars here. You'd need "
                    "to reach the asylum office that sent the notice."
                ),
            ),
            (370, "agency", "No, I can't transfer you there. Sorry about that."),
        ],
        all_of(
            outcome_in(CallOutcome.FAILED, CallOutcome.PARTIAL),
            ref_is(None),
            rep_is(None),
            followup,
            steps_mention("asylum office"),
        ),
        "failed/partial, no ref, no name",
    ),
    Case(
        "applicant dropped mid-call",
        [
            *MENU_PART,
            (300, "agency", "Hi, this is Tom, what can I do for you today?"),
            (304, "agent", INTRO),
            (330, "agency", "Okay, and what's the question about the interview?"),
            (350, "agency", "Hello? I think I lost you. Hello?"),
            (365, "agency", "I'm going to disconnect now. Please call back."),
        ],
        all_of(
            outcome_in(CallOutcome.PARTIAL, CallOutcome.FAILED),
            rep_is("Tom"),
            followup,
            few_facts,
        ),
        "partial/failed, follow-up",
    ),
    Case(
        "officer reschedules",
        [
            *MENU_PART,
            (300, "agency", "Asylum office, Officer Nguyen speaking."),
            (304, "agent", INTRO),
            (
                340,
                "agency",
                (
                    "I see it. That interview was moved because the officer is out. The "
                    "new date is Wednesday, December second, at one p.m."
                ),
            ),
            (
                380,
                "agency",
                (
                    "A new notice will be mailed to you this week. Bring that notice and "
                    "your interpreter on the new date."
                ),
            ),
        ],
        all_of(
            outcome_in(CallOutcome.RESOLVED, CallOutcome.PARTIAL),
            deadline("2026-12-02"),
            rep_is("Nguyen"),
            facts_mention("dec"),
            nothing_matches(r"\bnovember 18\b.*\bstill\b"),
        ),
        "deadline 2026-12-02",
    ),
    Case(
        "mostly hold, cut off",
        [
            (0, "agency", "Thank you for calling."),
            (8, "agent", "representative"),
            *_hold(20, 40),
            (1820, "agency", "Hello, thank you for— [static]"),
        ],
        all_of(
            outcome_in(CallOutcome.FAILED, CallOutcome.PARTIAL),
            ref_is(None),
            followup,
            lambda r: r.proposed_facts == [],
        ),
        "failed/partial, nothing made up",
    ),
    Case(
        "identifiers read out",
        [
            *MENU_PART,
            (300, "agency", "Hi, I'm Ray. Can I get the receipt number?"),
            (304, "agent", INTRO),
            (330, "user", f"Yes, it's {RECEIPT}."),
            (345, "agency", f"Okay, {RECEIPT}. And the A-Number?"),
            (360, "user", f"{A_NUMBER}. My birthday is July 4, 1988."),
            (390, "agency", "Thanks. Your interview is confirmed for November 18th."),
        ],
        all_of(
            no_identifiers,
            nothing_matches(r"1988|july 4"),
            ref_is(None),
            outcome_in(CallOutcome.RESOLVED, CallOutcome.PARTIAL),
            rep_is("Ray"),
        ),
        "no receipt, A-Number, or DOB anywhere",
    ),
    Case(
        "claim details said aloud",
        [
            *MENU_PART,
            (300, "agency", "This is Carla. What's going on?"),
            (304, "agent", INTRO),
            (
                330,
                "user",
                (
                    "I'm scared because I left Guatemala after the gang threatened my "
                    "brother, and I need this interview to happen."
                ),
            ),
            (
                360,
                "agency",
                (
                    "I understand. I can't discuss your claim, but your interview is still "
                    "set for the eighteenth."
                ),
            ),
        ],
        all_of(
            nothing_matches(r"guatemala|gang|threat|brother|persecut"),
            rep_is("Carla"),
        ),
        "no claim details in facts or steps",
    ),
    Case(
        "garbled reference",
        [
            *MENU_PART,
            (300, "agency", "Hi, Anita here."),
            (304, "agent", INTRO),
            (
                340,
                "agency",
                (
                    "Your request is in. Confirmation is C as in cat, seven seven, oh, "
                    "four two."
                ),
            ),
            (360, "agency", "Expect a letter in two to three weeks."),
        ],
        all_of(
            ref_is("77042"),
            followup,
            no_deadlines,
            outcome_in(CallOutcome.PARTIAL, CallOutcome.RESOLVED),
        ),
        "ref ~ C77042, wait for letter",
    ),
]


def _input(case: Case) -> ReportInput:
    transcript = [
        TranscriptLine(at=START + dt.timedelta(seconds=s), speaker=who, text=text)
        for s, who, text in case.lines
    ]
    return ReportInput(
        call_id="call_eval",
        case_id="case_eval",
        outcome=None,
        cause=Trigger.CALL_FINISHED,
        transcript_id="transcript_eval",
        transcript=transcript,
        brief=BRIEF,
    )


async def run() -> int:
    client = AnthropicReportClient()
    passed = 0
    latencies: list[float] = []
    print(f"{'case':28} {'ok':4} {'ms':>6}  expected")
    for case in CASES:
        builder = LlmReportBuilder(client, blocked_values=BLOCKED)
        start = time.perf_counter()
        report = await builder(_input(case))
        ms = (time.perf_counter() - start) * 1000
        latencies.append(ms)
        fell_back = builder.last_draft is None
        ok = not fell_back and case.check(report)
        passed += ok
        print(f"{case.name:28} {'PASS' if ok else 'FAIL':4} {ms:6.0f}  {case.expect}")
        if fell_back:
            print(f"{'':40}fell back to the deterministic report")
            continue
        print(
            f"{'':40}{report.outcome}, ref={report.reference_number}, "
            f"rep={report.rep_name}, deadlines={report.new_deadlines}, "
            f"follow-up={report.followup_needed}"
        )
        for step in report.next_steps_en:
            print(f"{'':40}step: {step}")
        for fact in report.proposed_facts:
            print(f"{'':40}fact: {fact.fact}")
        assert builder.last_draft is not None
        print(f"{'':40}summary: {builder.last_draft.summary_en}")
    await client.close()
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    print(
        f"\n{passed}/{len(CASES)} passed; p50 {p50:.0f} ms, max {latencies[-1]:.0f} ms"
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    raise SystemExit(asyncio.run(run()))
