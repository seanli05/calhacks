"""Text output for the playground: one block per runner step, plus the inspectors.

Plain ANSI color, off when stdout isn't a terminal or `NO_COLOR` is set. Compact by
default; verbose adds the raw model answers, 1c's cues, and each event's data.
"""

import json
import os
import sys
from collections.abc import Iterable

from app.contracts import CallState
from app.phone import menu, phase
from app.phone.menu import (
    AskUserAction,
    MenuAction,
    MenuDecision,
    MenuTurn,
    PressAction,
    SayAction,
)
from app.phone.observe import StepRecord
from app.phone.phase import HeardTurn
from app.phone.playground.script import Outcome
from app.phone.playground.session import CallSession
from app.phone.playground.tap import ModelCall

_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
_PAD = "  "


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def dim(text: str) -> str:
    return paint(text, "2")


def bold(text: str) -> str:
    return paint(text, "1")


def red(text: str) -> str:
    return paint(text, "31")


def green(text: str) -> str:
    return paint(text, "32")


def yellow(text: str) -> str:
    return paint(text, "33")


def cyan(text: str) -> str:
    return paint(text, "36")


def clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def clip(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe(action: MenuAction | None) -> str:
    match action:
        case None:
            return "no decision"
        case PressAction():
            return f'PRESS {action.digits} "{action.option_label_en}"'
        case SayAction():
            return f'SAY "{action.text}"'
        case AskUserAction():
            keys = ", ".join(f"{o.digits}={o.label_en}" for o in action.options)
            return f"ASK_USER [{keys}] default {action.default_option}"
    return "WAIT"


def _row(tag: str, text: str) -> str:
    return f"{_PAD}{dim(f'{tag:<7}')}{text}"


def outcome_lines(
    outcome: Outcome, session: CallSession, step: int, *, verbose: bool
) -> list[str]:
    lines = []
    if outcome.note:
        lines.append(_row("!!", yellow(outcome.note)))
    calls = session.llm.for_step(step)
    for record in outcome.records:
        lines += record_lines(record, calls, session, verbose=verbose)
    return lines


def record_lines(
    record: StepRecord,
    calls: list[ModelCall],
    session: CallSession,
    *,
    verbose: bool,
) -> list[str]:
    head = f"{clock(record.at_s)} {record.input}"
    if record.text and record.input != "heard":
        head += f" ({record.text})"
    lines = [dim(f"{_PAD}── {head} · in {record.state_before}")]
    if record.reading is not None:
        r = record.reading
        took = _ms(record, "classify")
        lines.append(
            _row(
                "1c",
                f"{bold(r.phase.upper())} {r.confidence:.2f} · {r.source}{took}  {dim(r.reason_en)}",
            )
        )
    for t in record.transitions:
        lines.append(
            _row(
                "state",
                cyan(f"{t.from_state} → {t.to_state}") + dim(f"  via {t.trigger}"),
            )
        )
    short = _short_of_threshold(record)
    if short:
        lines.append(_row("state", yellow(short)))
    if record.action is not None:
        lines += _action_lines(record, session)
    elif record.input == "heard" and record.state_before == CallState.MENU:
        if record.transitions:
            why = "the reading moved the call"
        elif "reprompt_while_asking" in record.flags:
            why = "the menu repeated; still waiting on the family"
        else:
            why = "none"
        lines.append(_row("1b", dim(f"no decision ({why})")))
    for sent in record.sent:
        lines.append(_row(">>", green(sent)))
    if record.logged:
        lines.append(_row("ev", ", ".join(record.logged)))
    if record.flags:
        lines.append(_row("!!", yellow(", ".join(record.flags))))
        why = _fallback_reason(record, calls)
        if why:
            lines.append(_row("", yellow(why)))
    repeats = _repeats(record, session)
    if repeats:
        lines.append(
            _row(
                "loop",
                f"same prompt heard {repeats}× before (code takes over at {menu.LOOP_CEILING})",
            )
        )
    if verbose:
        lines += _verbose_lines(record, calls, session)
    return lines


def _action_lines(record: StepRecord, session: CallSession) -> list[str]:
    action = record.action
    assert action is not None
    took = _ms(record, "decide")
    flag = yellow(" (fallback)") if action.fallback else ""
    lines = [_row("1b", bold(describe(action)) + flag + took)]
    if isinstance(action, AskUserAction):
        for number, option in enumerate(action.options, 1):
            mark = green("  ← default") if number == action.default_option else ""
            lines.append(
                _row("", f"{number}. {option.label_en}  (key {option.digits}){mark}")
            )
        request = next((q for q in reversed(session.relay.asked)), None)
        if request is not None:
            lines.append(
                _row(
                    "P1",
                    dim(
                        f"{request.question_id} · template {request.template} · "
                        f"timeout {request.timeout_s} s"
                    ),
                )
            )
    lines.append(_row("why", dim(action.reason_en)))
    return lines


def _short_of_threshold(record: StepRecord) -> str | None:
    """A reading that would have moved the call, had it been confident enough."""
    reading = record.reading
    if reading is None or record.transitions:
        return None
    rule = phase.RULES.get((record.state_before, reading.phase))
    if rule is None or reading.confidence >= rule.min_confidence:
        return None
    return (
        f"stays in {record.state_before}: {reading.phase} {reading.confidence:.2f} "
        f"< {rule.min_confidence:.2f} needed for {rule.trigger}"
    )


def _ms(record: StepRecord, name: str) -> str:
    ms = record.latency_ms.get(name)
    return dim(f" · {ms:,} ms") if ms is not None else ""


def _fallback_reason(record: StepRecord, calls: list[ModelCall]) -> str | None:
    """Why 1b fell back: the model failed, or the guard rejected its answer."""
    if record.action is None or not record.action.fallback:
        return None
    call = next((c for c in reversed(calls) if c.kind == "menu"), None)
    if call is None:
        return "no model call (code took over)"
    if call.error:
        return f"model call failed: {call.error}"
    if isinstance(call.output, MenuDecision):
        problem = menu.check_action(call.output.action)
        if problem:
            return f"guard rejected {describe(call.output.action)}: {problem}"
    return None


def _repeats(record: StepRecord, session: CallSession) -> int:
    """Earlier menu prompts like this one; an estimate, since the runner may join a
    prompt that speech-to-text split in two."""
    if (
        record.input != "heard"
        or record.state_before != CallState.MENU
        or not record.text
    ):
        return 0
    turns = []
    for earlier in session.records:
        if earlier is record:
            break
        if (
            earlier.input == "heard"
            and earlier.text
            and earlier.state_before == CallState.MENU
        ):
            action = earlier.action or menu.WaitAction(kind="wait", reason_en="-")
            turns.append(MenuTurn(heard=earlier.text, action=action))
    return len(menu.find_repeats(record.text, turns))


def _verbose_lines(
    record: StepRecord, calls: list[ModelCall], session: CallSession
) -> list[str]:
    lines = []
    for call in calls:
        raw = call.output.model_dump_json() if call.output is not None else call.error
        tag = "raw 1c" if call.kind == "phase" else "raw 1b"
        lines.append(_row(tag, dim(f"[{call.source}, {call.ms} ms] {raw}")))
    if record.input == "heard" and record.text:
        history = [
            HeardTurn(text=r.text, at_s=r.at_s, phase=r.reading.phase)
            for r in session.records
            if r is not record
            and r.reading is not None
            and r.text
            and r.at_s < record.at_s
        ]
        cues = phase.read_cues(record.text, record.at_s, history)
        on = [
            name
            for name, value in (
                ("introduces self", cues.introduces_self),
                ("asks caller", cues.asks_caller),
                ("says automated", cues.says_automated),
                ("offers options", cues.offers_options),
                ("hold language", cues.hold_language),
            )
            if value
        ]
        lines.append(
            _row(
                "cues",
                dim(
                    f"{', '.join(on) or 'none'} · closest earlier {cues.closest_earlier:.0%}"
                ),
            )
        )
    return lines


# Inspectors


def question_hint(session: CallSession) -> str | None:
    """What the line or the family can do next, when the runner is waiting on them."""
    question = session.relay.open
    if question is None:
        if session.state == CallState.BRIDGING and not session.ended:
            return yellow(
                f"{_PAD}?  the applicant's phone is ringing: /user answers, "
                "/user unreachable, or keep talking as the rep"
            )
        return None
    left = (question.deadline - session.clock.now()).total_seconds()
    return yellow(
        f"{_PAD}?  open question, {left:.0f} s left: type 1-{len(question.request.options_en)} "
        "to answer as the family, Enter for no answer (timeout), or keep pasting lines"
    )


def prompt_text(call: ModelCall | None) -> str:
    """The user message of the last model call; the system prompt is static."""
    if call is None:
        return "(no model call of this kind yet)"
    head = f"=== {call.kind} prompt, step {call.step} ({call.source}, {call.ms} ms)"
    return f"{bold(head)}\n{call.user}"


def brief_text(session: CallSession) -> str:
    return json.dumps(session.brief, indent=2, ensure_ascii=False)


def state_lines(session: CallSession) -> list[str]:
    lines = [
        f"state     {bold(session.state)}{'  (call ended)' if session.ended else ''}",
        f"clock     {clock(session.now_s)}",
        f"goal      {session.brief.get('call_goal_en')}",
    ]
    question = session.relay.open
    if question is not None:
        lines.append(
            f"question  {question.request.question_id}: {question.request.options_en}"
        )
    if session.llm.force_phase is not None:
        lines.append(f"armed     next phase reading: {session.llm.force_phase.phase}")
    if session.llm.fail_next:
        lines.append(
            f"armed     next {', '.join(sorted(session.llm.fail_next))} call fails"
        )
    if session.report is not None:
        lines.append(f"report    outcome {session.report.outcome}")
    return lines


def history_lines(session: CallSession) -> list[str]:
    lines = []
    for index, (step, outcome) in enumerate(zip(session.steps, session.outcomes)):
        what = step.do + (f' "{clip(step.text, 50)}"' if step.do == "heard" else "")
        got = (
            ""
            if outcome is None
            else f" → {describe(outcome.action)} · {outcome.state}"
        )
        lines.append(f"#{index:<3}{what}{dim(got)}")
    return lines or ["(no steps yet)"]


def event_lines(session: CallSession) -> list[str]:
    return [
        f"{clock((e.created_at - session.started).total_seconds())}  {e.type}  "
        f"{dim(json.dumps(e.data, default=str))}"
        for e in session.log.events
    ] or ["(no events yet)"]


def print_lines(lines: Iterable[str]) -> None:
    for line in lines:
        print(line)
