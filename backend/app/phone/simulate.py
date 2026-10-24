"""Run one whole call against a text phone tree, with real Claude for 1b and 1c.
Costs a little; not a test.

    python -m app.phone.simulate --list               # from backend/
    python -m app.phone.simulate --tree speech_federal
    python -m app.phone.simulate --tree keypad_state --interactive
    python -m app.phone.simulate --tree speech_federal --hold-limit-s 20

Needs ANTHROPIC_API_KEY (env or the repo-root .env). Everything else is a fake:
the line is `FakeTelephony` playing a tree from `sim_trees.py`, and the database
and relay are in memory. Time is real (`SystemClock`): a real Claude request
takes real time, which `FakeClock` can't wait for, and the latency against menu
timeouts is part of what the simulator shows. Holds are a few seconds.

`--interactive` asks you the ask_user questions at the console; otherwise the
tree's scripted answers are used, then none (the default).
"""

import argparse
import asyncio
import logging
import statistics
import sys
from datetime import UTC, datetime

from app.contracts import AskUserReply, AskUserRequest, CallJob, CallReport
from app.phone.clock import SystemClock, with_timeout
from app.phone.fakes import (
    Answer,
    FakeCallStore,
    FakeCaseReader,
    FakeEventLog,
    FakeNumberSource,
    FakeRelay,
    FakeTelephony,
)
from app.phone.guard import GuardedTelephony
from app.phone.llm import AnthropicLlmClient
from app.phone.observe import StepRecord
from app.phone.ports import CallDeps, Clock
from app.phone.runner import RunnerConfig, run_call
from app.phone.sim_line import PhoneTree, Tree
from app.phone.sim_trees import SIM_BRIEF, TREES
from app.settings import get_settings

CASE_ID = "case_sim"
USER_ID = "user_sim"
BRIEF_ID = "brief_sim"
SIM_BLOCKED = ("A123456789", "IOE0123456789", "1990-03-14")
"""Made-up identifiers for the guard to block; no real person's."""
_CLIP = 96


class ConsoleRelay:
    """ask_user at the terminal: type the option number, or wait for the default."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def ask_user(self, request: AskUserRequest) -> AskUserReply:
        print("\n  ?? The applicant is asked (type a number and Enter):")
        for number, option in enumerate(request.options_en, 1):
            marker = " (default)" if number == request.default_option else ""
            print(f"     {number}. {option}{marker}")
        loop = asyncio.get_running_loop()
        line: asyncio.Future[str] = loop.create_future()
        loop.add_reader(
            sys.stdin, lambda: line.done() or line.set_result(sys.stdin.readline())
        )
        try:
            text = await with_timeout(self._clock, line, request.timeout_s)
            choice = int(text.strip())
        except TimeoutError:
            choice = request.default_option
        except ValueError:
            choice = request.default_option
        finally:
            loop.remove_reader(sys.stdin)
        if not 1 <= choice <= len(request.options_en):
            choice = request.default_option
        return AskUserReply(question_id=request.question_id, choice=choice)


class Timeline:
    """Prints each `StepRecord` as it happens, and keeps latencies for the summary."""

    def __init__(self) -> None:
        self.latencies: dict[str, list[int]] = {"classify": [], "decide": []}

    def __call__(self, step: StepRecord) -> None:
        self._print(step)
        for name, ms in step.latency_ms.items():
            self.latencies.setdefault(name, []).append(ms)

    def _print(self, step: StepRecord) -> None:
        head = f"{step.at_s:7.1f}s  {step.state_before:<14} {step.input}"
        if step.text:
            head += f'  "{_clip(step.text)}"'
        print(head)
        pad = " " * 10
        if step.reading is not None:
            r = step.reading
            ms = step.latency_ms.get("classify")
            took = f" · {ms} ms" if ms is not None else ""
            print(
                f"{pad}1c  {r.phase} {r.confidence:.2f} ({r.source}){took}: {r.reason_en}"
            )
        if step.action is not None:
            ms = step.latency_ms.get("decide")
            took = f" · {ms} ms" if ms is not None else ""
            print(f"{pad}1b  {_describe(step.action)}{took}")
        for sent in step.sent:
            print(f"{pad}>>  {_clip(sent)}")
        for transition in step.transitions:
            print(
                f"{pad}==  {transition.from_state} -> {transition.to_state} "
                f"({transition.trigger})"
            )
        if step.flags:
            print(f"{pad}!!  {', '.join(step.flags)}")
        if step.logged:
            print(f"{pad}ev  {', '.join(step.logged)}")


def _describe(action: object) -> str:
    kind = getattr(action, "kind", "?")
    detail = {
        "press": lambda a: f'press {a.digits} ("{a.option_label_en}")',
        "say": lambda a: f'say "{a.text}"',
        "ask_user": lambda a: (
            "ask_user: "
            + " | ".join(f"{o.digits}={o.label_en}" for o in a.options)
            + f" (default {a.default_option})"
        ),
    }.get(kind, lambda a: kind)(action)
    fallback = " [fallback]" if getattr(action, "fallback", False) else ""
    return f"{detail}{fallback} — {getattr(action, 'reason_en', '')}"


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _CLIP else text[: _CLIP - 1] + "…"


async def simulate(
    tree: Tree, *, interactive: bool = False, hold_limit_s: float | None = None
) -> tuple[CallReport, PhoneTree, FakeCallStore, FakeEventLog, Timeline]:
    clock = SystemClock()
    numbers = FakeNumberSource(
        verified={CASE_ID: "+18005550100"}, users={USER_ID: "+15555550123"}
    )
    phone = PhoneTree(tree, clock)
    line = FakeTelephony(numbers, clock, responder=phone)
    phone.attach(line)
    relay = (
        ConsoleRelay(clock)
        if interactive
        else FakeRelay(clock, [Answer(choice, after_s=4) for choice in tree.answers])
    )
    store, log = FakeCallStore(), FakeEventLog()
    deps = CallDeps(
        telephony=GuardedTelephony(line, SIM_BLOCKED),
        relay=relay,
        cases=FakeCaseReader({BRIEF_ID: SIM_BRIEF}),
        calls=store,
        events=log,
        clock=clock,
    )
    job = CallJob(
        case_id=CASE_ID,
        user_id=USER_ID,
        brief_id=BRIEF_ID,
        user_language="es",
        consent_at=datetime.now(UTC),
        consent_message_id="msg_sim",
        max_hold_minutes=60,
    )
    timeline = Timeline()
    report = await run_call(
        "job_sim",
        job,
        deps,
        llm=AnthropicLlmClient(),
        observer=timeline,
        config=RunnerConfig(hold_limit_s=hold_limit_s),
    )
    return report, phone, store, log, timeline


def _summary(
    report: CallReport,
    phone: PhoneTree,
    store: FakeCallStore,
    log: FakeEventLog,
    timeline: Timeline,
) -> None:
    [call] = store.calls.values()
    print("\n--- summary")
    print(f"tree path:  {' > '.join(phone.visited)}")
    print(f"states:     {' > '.join(call.states)}")
    print(f"events:     {', '.join(log.types)}")
    print(f"outcome:    {report.outcome}  next steps: {report.next_steps_en}")
    for name, values in timeline.latencies.items():
        if values:
            print(
                f"{name + ':':<11} n={len(values)} median={statistics.median(values):.0f} ms "
                f"max={max(values)} ms"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", choices=sorted(TREES))
    parser.add_argument("--list", action="store_true", help="list the trees")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--hold-limit-s", type=float, default=None)
    args = parser.parse_args()
    if args.list or not args.tree:
        for tree in TREES.values():
            print(f"{tree.name:<22} {tree.about}")
        return
    if not get_settings().anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY isn't set (env or the repo-root .env).")
    logging.basicConfig(
        level=logging.WARNING, format="          %(levelname)s %(message)s"
    )
    tree = TREES[args.tree]
    print(f"=== {tree.name}: {tree.about}\n")
    result = asyncio.run(
        simulate(tree, interactive=args.interactive, hold_limit_s=args.hold_limit_s)
    )
    _summary(*result)


if __name__ == "__main__":
    main()
