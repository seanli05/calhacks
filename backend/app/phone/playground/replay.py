"""Replay a saved script without prompts and check each step's expectations.

Real Claude by default, so a replay costs a little and varies run to run: that's why
expectations are properties. With `--fake` it answers from the script's recorded
model outputs instead, which checks the plumbing (states, ask_user, timers) for free.
History builds from the live answers, so a model that drifts shows up downstream.
"""

import statistics
from dataclasses import dataclass, field

from app.phone.playground.render import bold, clip, describe, dim, green, red
from app.phone.playground.script import (
    CONTROL_STEPS,
    Outcome,
    Script,
    ScriptStep,
    check,
)
from app.phone.playground.session import CallSession
from app.phone.playground.tap import ModelKind, Recorded, TapLlm
from app.phone.runner import RunnerConfig


@dataclass
class Row:
    index: int
    step: ScriptStep
    outcome: Outcome
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def recorded_answers(script: Script) -> dict[tuple[int, ModelKind], Recorded]:
    return {
        (index, kind): recorded
        for index, step in enumerate(script.steps)
        for kind, recorded in step.model.items()
    }


async def replay(
    script: Script,
    llm: TapLlm,
    *,
    config: RunnerConfig | None = None,
    step_wait_s: float | None = None,
) -> tuple[list[Row], CallSession]:
    session = CallSession(llm, goal=script.goal, config=config, **_wait(step_wait_s))
    await session.start()
    rows = []
    try:
        for index, step in enumerate(script.steps):
            outcome = await session.run(step.model_copy(update={"model": {}}))
            if outcome is None or isinstance(step, CONTROL_STEPS):
                continue
            problems = check(step.expect, outcome) if step.expect else []
            rows.append(Row(index, step, outcome, problems))
    finally:
        await session.close()
    return rows, session


def _wait(step_wait_s: float | None) -> dict[str, float]:
    return {} if step_wait_s is None else {"step_wait_s": step_wait_s}


def _input(step: ScriptStep) -> str:
    match step.do:
        case "heard":
            return f'"{clip(step.text, 38)}"'
        case "reply":
            return f"reply {step.choice}"
        case "line":
            return step.event
        case "sound":
            return f"{step.sound} {step.seconds:.0f}s"
        case "wait":
            return f"wait {step.seconds:.0f}s"
    return step.do


def _expected(step: ScriptStep) -> str:
    e = step.expect
    if e is None:
        return "-"
    parts = []
    if e.kind:
        parts.append("/".join(e.kind))
    if e.digits:
        parts.append("keys " + "/".join(e.digits))
    if e.options:
        parts.append("opts " + ",".join(e.options))
    if e.say_matches:
        parts.append(f"/{e.say_matches}/")
    if e.state:
        parts.append(f"→ {e.state}")
    return " ".join(parts)


def _got(outcome: Outcome) -> str:
    action = outcome.action
    text = "none" if action is None else describe(action)
    return f"{clip(text, 34)} → {outcome.state}"


def table_lines(rows: list[Row]) -> list[str]:
    lines = [
        bold(
            f"{'#':>3}  {'input':<40} {'expected':<34} {'got':<46} {'1c ms':>6} {'1b ms':>6}  ok"
        )
    ]
    classify: list[int] = []
    decide: list[int] = []
    for row in rows:
        ms = {
            name: sum(r.latency_ms.get(name, 0) for r in row.outcome.records)
            for name in ("classify", "decide")
        }
        if ms["classify"]:
            classify.append(ms["classify"])
        if ms["decide"]:
            decide.append(ms["decide"])
        ok = green("PASS") if row.passed else red("FAIL")
        lines.append(
            f"{row.index:>3}  {_input(row.step):<40} {clip(_expected(row.step), 34):<34} "
            f"{_got(row.outcome):<46} {ms['classify'] or '':>6} {ms['decide'] or '':>6}  {ok}"
        )
        for problem in row.problems:
            lines.append(dim(f"{'':5}{problem}"))
    passed = sum(row.passed for row in rows)
    lines.append("")
    lines.append(f"{passed}/{len(rows)} passed")
    for name, values in (("1c classify", classify), ("1b decide", decide)):
        if values:
            lines.append(
                f"{name}: n={len(values)} p50 {statistics.median(values):.0f} ms, "
                f"max {max(values)} ms"
            )
    return lines
