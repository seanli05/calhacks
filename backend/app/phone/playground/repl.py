"""The interactive loop: parse what you type, run it on the session, print the steps."""

import asyncio
import re
from dataclasses import dataclass
from typing import get_args

from app.phone.llm import LlmClient
from app.phone.menu import MenuDecision
from app.phone.menu_prompts import MENU_SYSTEM
from app.phone.phase_prompts import PHASE_SYSTEM
from app.phone.playground import render
from app.phone.playground.render import bold, dim, red, yellow
from app.phone.playground.script import (
    CONTROL_STEPS,
    FailStep,
    HeardStep,
    LineEventName,
    LineStep,
    PhaseStep,
    ReplyStep,
    ScriptStep,
    SoundStep,
    TimeoutStep,
    WaitStep,
    save,
    script_path,
)
from app.phone.playground.session import CallSession, rebuild
from app.phone.playground.tap import (
    TYPED_HELP,
    ModelKind,
    Recorded,
    TapLlm,
    parse_typed_action,
)
from app.phone.runner import RunnerConfig

HELP = """\
Paste what the line says. Prefix +30s or +3m to set the time since the last line
(default 10 s). While a question is open: a number answers as the family, Enter
means they never answer.

Line     /answered  /no-answer  /hangup  /music 2m  /silence 20s  /wait 5m
Family   /reply N  /timeout  /user answers|unreachable|left
Steer    /phase menu|hold|human|unclear [confidence]   force the next 1c reading
         /fail menu|phase                               fail the next model call
Look     /prompt [menu|phase] [system]  /brief  /state  /history  /events  /verbose
Session  /goal <text> (restarts)  /undo  /reset  /save <name> [about]  /save! …  /quit"""

_TYPED_GRACE_S = 0.1
_DURATION = re.compile(r"^(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?$")
_GAP = re.compile(r"^\+(\S+)\s+(.+)$", re.DOTALL)
_USER_EVENTS: dict[str, LineEventName] = {
    "answers": "user_answered",
    "unreachable": "user_unreachable",
    "left": "user_left",
}
_LINE_COMMANDS: dict[str, LineEventName] = {
    "answered": "agency_answered",
    "no-answer": "no_answer",
    "hangup": "agency_hung_up",
}
_META = {
    "prompt", "brief", "goal", "state", "history", "events", "verbose",
    "undo", "reset", "save", "save!", "help", "quit", "exit",
}  # fmt: skip


@dataclass(frozen=True)
class Meta:
    """A playground command that isn't a call step."""

    name: str
    arg: str = ""


type Command = ScriptStep | Meta


def parse_duration(text: str) -> float:
    match = _DURATION.match(text.strip())
    if not text.strip() or match is None or not any(match.groups()):
        raise ValueError(f"not a duration: {text!r} (try 30s, 3m, 1m30s)")
    minutes, seconds = match.groups()
    return int(minutes or 0) * 60 + float(seconds or 0)


def parse(line: str, *, question_open: bool) -> Command | None:
    """What a typed line means. None: nothing to do. Raises ValueError with a hint."""
    text = line.strip()
    if not text:
        return TimeoutStep() if question_open else None
    if question_open and text.isdigit():
        return ReplyStep(choice=int(text))
    if not text.startswith("/"):
        gap = _GAP.match(text)
        if gap:
            return HeardStep(
                text=gap.group(2).strip(), after_s=parse_duration(gap.group(1))
            )
        return HeardStep(text=text)

    name, _, arg = text[1:].partition(" ")
    name, arg = name.lower(), arg.strip()
    match name:
        case "reply":
            if not arg.isdigit():
                raise ValueError("/reply N, with N the option number")
            return ReplyStep(choice=int(arg))
        case "timeout":
            return TimeoutStep()
        case "wait":
            return WaitStep(seconds=parse_duration(arg))
        case "music" | "silence":
            return SoundStep(sound=name, seconds=parse_duration(arg))
        case "user":
            if arg not in _USER_EVENTS:
                raise ValueError("/user answers|unreachable|left")
            return LineStep(event=_USER_EVENTS[arg])
        case "phase":
            reading, _, confidence = arg.partition(" ")
            if reading not in ("menu", "hold", "human", "unclear"):
                raise ValueError("/phase menu|hold|human|unclear [confidence]")
            return PhaseStep(
                phase=reading, confidence=float(confidence) if confidence else 0.9
            )
        case "fail":
            if arg not in get_args(ModelKind.__value__):
                raise ValueError("/fail menu|phase")
            return FailStep(kind=arg)
        case _ if name in _LINE_COMMANDS:
            return LineStep(event=_LINE_COMMANDS[name])
        case _ if name in _META:
            return Meta(name, arg)
    raise ValueError(f"unknown command /{name}; /help lists them")


@dataclass
class Options:
    inner: LlmClient | None
    """The real model, or None for `--fake`."""
    goal: str | None = None
    verbose: bool = False
    config: RunnerConfig | None = None


class Repl:
    def __init__(self, options: Options) -> None:
        self.options = options
        self.verbose = options.verbose
        self.goal = options.goal
        self.session: CallSession | None = None

    @property
    def fake(self) -> bool:
        return self.options.inner is None

    def make_llm(
        self, answers: dict[tuple[int, ModelKind], Recorded], until: int
    ) -> TapLlm:
        return TapLlm(
            self.options.inner,
            typed=self._typed if self.fake else None,
            cassette=answers,
            cassette_until=until,
        )

    def _new_session(self) -> CallSession:
        return CallSession(
            self.make_llm({}, 0),
            goal=self.goal,
            config=self.options.config,
            step_wait_s=None if self.fake else 60.0,
        )

    async def _typed(self, user_prompt: str) -> MenuDecision | None:
        """`--fake`: you answer as the menu model."""
        # 1c runs alongside and may move the call out of the menu, which discards this
        # call: let it, before a prompt that a cancelled input thread would swallow.
        await asyncio.sleep(_TYPED_GRACE_S)
        print(dim(f"  model? {TYPED_HELP}"))
        while True:
            text = await asyncio.to_thread(input, "  model› ")
            try:
                action = parse_typed_action(text)
            except ValueError as exc:
                print(red(f"  {exc}"))
                continue
            return None if action is None else MenuDecision(action=action)

    async def run(self) -> None:
        self.session = self._new_session()
        self._header()
        outcome = await self.session.start()
        render.print_lines(
            render.outcome_lines(outcome, self.session, -1, verbose=self.verbose)
        )
        try:
            while True:
                session = self.session
                hint = render.question_hint(session)
                if hint:
                    print(hint)
                prompt = f"[{session.state} {render.clock(session.now_s)}] › "
                try:
                    line = await asyncio.to_thread(input, prompt)
                except EOFError:
                    break
                try:
                    command = parse(line, question_open=session.relay.open is not None)
                except ValueError as exc:
                    print(red(f"  {exc}"))
                    continue
                if command is None:
                    continue
                if isinstance(command, Meta):
                    if not await self._meta(command):
                        break
                    continue
                await self._step(command)
        finally:
            if self.session is not None:
                await self.session.close()

    async def _step(self, step: ScriptStep) -> None:
        session = self.session
        assert session is not None
        index = len(session.steps)
        was_ended = session.ended
        outcome = await session.run(step)
        if isinstance(step, CONTROL_STEPS):
            what = (
                f"{step.phase} {step.confidence}"
                if isinstance(step, PhaseStep)
                else "fail"
            )
            print(
                dim(
                    f"  armed: next {'phase' if isinstance(step, PhaseStep) else step.kind} call → {what}"
                )
            )
            return
        assert outcome is not None
        render.print_lines(
            render.outcome_lines(outcome, session, index, verbose=self.verbose)
        )
        if session.ended and not was_ended and session.report is not None:
            report = session.report
            print(bold(f"  call ended · outcome {report.outcome}"))
            print(dim(f"  next steps: {report.next_steps_en}"))
            print(dim("  /undo, /reset, or /save <name>"))

    async def _meta(self, command: Meta) -> bool:
        """Returns False to quit."""
        session = self.session
        assert session is not None
        arg = command.arg
        match command.name:
            case "help":
                print(HELP)
            case "quit" | "exit":
                return False
            case "verbose":
                self.verbose = not self.verbose
                print(dim(f"  verbose {'on' if self.verbose else 'off'}"))
            case "brief":
                print(render.brief_text(session))
            case "state":
                render.print_lines(render.state_lines(session))
            case "history":
                render.print_lines(render.history_lines(session))
            case "events":
                render.print_lines(render.event_lines(session))
            case "prompt":
                words = arg.split()
                kind: ModelKind = "phase" if "phase" in words else "menu"
                if "system" in words:
                    print(bold(f"=== {kind} system prompt (static, cached)"))
                    print(PHASE_SYSTEM if kind == "phase" else MENU_SYSTEM)
                else:
                    print(render.prompt_text(session.llm.last(kind)))
            case "goal":
                if not arg:
                    print(f"  goal: {session.brief.get('call_goal_en')}")
                    return True
                self.goal = arg
                await self._restart([], "restarted the call with the new goal")
            case "reset":
                await self._restart([], "new call")
            case "undo":
                if not session.steps:
                    print(dim("  nothing to undo"))
                    return True
                dropped = session.steps[-1]
                await self._restart(
                    session.steps[:-1],
                    f"undid {dropped.do}; redid {len(session.steps) - 1} steps from recorded answers",
                    answers=session.recorded_model(),
                )
            case "save" | "save!":
                self._save(arg, overwrite=command.name == "save!")
        return True

    async def _restart(
        self,
        steps: list[ScriptStep],
        note: str,
        *,
        answers: dict[tuple[int, ModelKind], Recorded] | None = None,
    ) -> None:
        old = self.session
        assert old is not None
        await old.close()
        self.session = await rebuild(
            steps,
            self.make_llm,
            answers or {},
            goal=self.goal,
            config=self.options.config,
            step_wait_s=None if self.fake else 60.0,
        )
        print(yellow(f"  {note}"))
        render.print_lines(render.state_lines(self.session))

    def _save(self, arg: str, *, overwrite: bool) -> None:
        session = self.session
        assert session is not None
        name, _, about = arg.partition(" ")
        if not name:
            print(red("  /save <name> [about]"))
            return
        path = script_path(name)
        if path.exists() and not overwrite:
            print(red(f"  {path} exists; /save! {arg} to overwrite"))
            return
        save(session.to_script(about.strip()), path)
        print(dim(f"  saved {len(session.steps)} steps to {path}"))

    def _header(self) -> None:
        session = self.session
        assert session is not None
        model = (
            "fake (you answer for 1b; 1c uses its cue fallback)"
            if self.fake
            else "real Claude"
        )
        print(bold("phone agent playground") + dim(f" · {model}"))
        print(dim(f"brief: demo_brief · goal: {session.brief.get('call_goal_en')}"))
        print(dim("the agent is dialing; paste what the line says. /help for commands"))
