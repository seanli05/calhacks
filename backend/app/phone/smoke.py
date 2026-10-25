"""Live smoke test for the real phone line (person 4). A manual dev tool, never
wired into the app (a test checks nothing in `app` imports it).

    python -m app.phone.smoke                 # the demo case's line; you type actions
    python -m app.phone.smoke --runner        # the full call runner drives the call
    python -m app.phone.smoke --own-number    # your phone plays the agency
    python -m app.phone.smoke --case CASE_ID  # another case (still the mock line only)
    python -m app.phone.smoke --runner --bridge   # your phone plays the applicant
    python -m app.phone.smoke --bridge --language en  # the join prompt in English
    python -m app.phone.smoke --runner --bridge   # then type `listen` to sit in

It serves the phone routes itself, in this process, because a call's line lives
in memory: stop the backend first, and point ngrok and `PUBLIC_BASE_URL` at
`--port`. Interactive commands: `say <text>`, `keys <digits>`, `bridge` (with
`--bridge`: ring your phone; a key press there joins you, and the agency leg
follows), `listen` (with `--bridge`: ring your phone to sit in, muted, the way a
user's WhatsApp request does), `hangup`. With `--runner`, type a number to answer
the applicant's question, `listen`, `end` (end the call the way a user's WhatsApp
"hang up now" does), or `hangup`.

What it may dial, without weakening rule 2:

- by default, the case's number from `DbNumberSource` (rule 2 and C40 for real),
  and only if that number is the mock agency line (`MockLineOnly`), so a smoke
  run can never call a real agency;
- with `--own-number`, `PHONE_SMOKE_DIAL_NUMBER` from your `.env`, through
  `SmokeNumberSource`, which exists only here. The number is never printed.

It rings only `PHONE_SMOKE_USER_NUMBER` as the applicant (or listener), and only
with `--bridge`
(C6 holds: the line reads it from the number source; it's never printed).

Smoke calls are ours to our own lines, not a user's call, so no `calls` row or
consent message exists: the runner gets fake stores and a fake job, and nothing
is written to the shared database. What the line hears is printed to this
terminal only, never logged. The C35 guard is always on.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from loguru import logger as pipecat_logger

from app.contracts import CallJob
from app.contracts.common import CaseId, UserId
from app.db import reads
from app.db.ids import new_id
from app.db.reset import demo_brief
from app.phone.adapters import DbCaseReader, DbNumberSource, load_blocked_values
from app.phone.call_lines import JOIN_PROMPTS
from app.phone.clock import SystemClock
from app.phone.control import request_hang_up, request_listen_in
from app.phone.fakes import FakeCallStore, FakeCaseReader, FakeEventLog
from app.phone.guard import BlockedIdentifier, GuardedTelephony
from app.phone.line import (
    Heard,
    LineEvent,
    ListenRequested,
    NonSpeech,
    Overheard,
    UserAnswered,
)
from app.phone.observe import StepRecord
from app.phone.playground.render import clip, describe
from app.phone.playground.tap import ConsoleRelay
from app.phone.ports import CallDeps, CaseReader, LineClosed, NumberSource
from app.phone.routes import router
from app.phone.runner import run_call
from app.phone.simulate import SIM_BLOCKED
from app.phone.twilio_line import TwilioTelephony
from app.phone.twilio_rest import TwilioCalls
from app.phone.twilio_urls import LineUrls
from app.settings import Settings

RUNS_DIR = Path(__file__).resolve().parents[2] / "smoke_runs"
"""`backend/smoke_runs/`, git-ignored: one JSON-lines file per run."""
SMOKE_LANGUAGE = "es"
"""The smoke job's language by default (`--language`), and so the join gate's."""
OWN_CASE = "case_smoke"
OWN_BRIEF = "brief_smoke"
SMOKE_USER = "user_smoke"
_SERVER_START_S = 10.0

_LIVE_CALL = (
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_agent_number",
    "cartesia_api_key",
    "cartesia_agent_voice_id",
    "public_base_url",
)


class SmokeSettings(Settings):
    phone_smoke_dial_number: str = ""
    """Your own phone, for `--own-number` only. Never commit it."""
    phone_smoke_user_number: str = ""
    """Your own phone as the applicant, for `--bridge` only. Never commit it."""


class SmokeRefused(Exception):
    """The smoke test won't dial this. The message never contains a number."""


def _e164(number: str, name: str) -> str:
    if not (number.startswith("+") and number[1:].isdigit()):
        raise SmokeRefused(f"{name} must be E.164 (+15551234567)")
    return number


class _RingsOnlyYou:
    """The applicant's number: your own phone with `--bridge`, else nobody."""

    def __init__(self, applicant: str | None) -> None:
        self._applicant = (
            None if applicant is None else _e164(applicant, "PHONE_SMOKE_USER_NUMBER")
        )

    async def user_number(self, user_id: UserId) -> str:
        if self._applicant is None:
            raise SmokeRefused("the smoke test rings the applicant only with --bridge")
        return self._applicant


class MockLineOnly(_RingsOnlyYou):
    """A `NumberSource` that passes on only the mock agency line."""

    def __init__(
        self, inner: NumberSource, mock_number: str, applicant: str | None = None
    ) -> None:
        super().__init__(applicant)
        self._inner = inner
        self._mock_number = mock_number

    async def official_dial_number(self, case_id: CaseId) -> str:
        number = await self._inner.official_dial_number(case_id)
        if not self._mock_number or number != self._mock_number:
            raise SmokeRefused(
                f"case {case_id}'s number isn't the mock agency line; set "
                "DEMO_DIAL_NUMBER to it or pick a seeded case"
            )
        return number


class SmokeNumberSource(_RingsOnlyYou):
    """Your own phone as the agency. Only `--own-number` builds one."""

    def __init__(self, number: str, applicant: str | None = None) -> None:
        super().__init__(applicant)
        self._number = _e164(number, "PHONE_SMOKE_DIAL_NUMBER")

    async def official_dial_number(self, case_id: CaseId) -> str:
        return self._number


def missing_settings(settings: SmokeSettings, args: argparse.Namespace) -> list[str]:
    needed = list(_LIVE_CALL)
    needed.append(
        "phone_smoke_dial_number" if args.own_number else "twilio_mock_agency_number"
    )
    if args.runner:
        needed.append("anthropic_api_key")
    if args.bridge:
        needed.append("phone_smoke_user_number")
    return [name.upper() for name in needed if not getattr(settings, name)]


# Printing


class Printer:
    """Prints the run to the terminal and, unless `run_file` is None, saves it as
    JSON lines there. The file holds what was heard and said: it stays on this
    machine (`smoke_runs/` is git-ignored) and is never logged."""

    def __init__(self, run_file: Path | None = None) -> None:
        self._start = time.monotonic()
        self._file = None
        if run_file is not None:
            run_file.parent.mkdir(exist_ok=True)
            self._file = run_file.open("a", encoding="utf-8")
            print(f"saving this run to {run_file}", flush=True)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def save(self, kind: str, **data: Any) -> None:
        if self._file is not None:
            row = {"t": round(self._elapsed(), 2), "kind": kind, **data}
            self._file.write(json.dumps(row, default=str) + "\n")
            self._file.flush()

    def line(self, text: str) -> None:
        print(f"[+{self._elapsed():6.1f}s] {text}", flush=True)
        self.save("note", text=text)

    def event(self, event: LineEvent) -> None:
        match event:
            case Heard(text=text):
                self._print(f'heard      "{text}"')
            case NonSpeech(sound=sound, seconds=seconds):
                self._print(f"non_speech {sound} {seconds:.0f} s")
            case Overheard(speaker=speaker, text=text):
                self._print(f'{speaker + ":":<10} "{text}"')
            case _:
                self._print(event.kind)
        self.save("line_event", event=event.model_dump())

    def step(self, record: StepRecord) -> None:
        moved = f"{record.state_before} → {record.state_after}"
        self._print(f"{record.input:<18} {moved if record.transitions else ''}")
        if record.text:
            self._detail("text", f'"{clip(record.text, 110)}"')
        if record.reading is not None:
            reading = record.reading
            self._detail(
                "phase",
                f"{reading.phase} {reading.confidence:.2f} ({reading.source}): "
                f"{reading.reason_en}",
            )
        if record.action is not None:
            self._detail(
                "action", f"{describe(record.action)}: {record.action.reason_en}"
            )
        for sent in record.sent:
            self._detail("sent", sent)
        if record.latency_ms:
            timings = " · ".join(f"{k} {v} ms" for k, v in record.latency_ms.items())
            self._detail("latency", timings)
        if record.flags:
            self._detail("flags", " ".join(record.flags))
        self.save("step", record=record.model_dump(mode="json"))

    def _print(self, text: str) -> None:
        print(f"[+{self._elapsed():6.1f}s] {text}", flush=True)

    def _detail(self, label: str, text: str) -> None:
        print(f"{'':11}{label:<8}{text}", flush=True)

    def _elapsed(self) -> float:
        return time.monotonic() - self._start


def run_file_for(mode: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return RUNS_DIR / f"{stamp}-{mode}.jsonl"


class Keyboard:
    """Lines typed at the terminal, read by the event loop rather than a thread, so
    the script can exit while nobody is typing."""

    def __init__(self) -> None:
        self._lines: asyncio.Queue[str | None] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._fd = sys.stdin.fileno()
        self._loop.add_reader(self._fd, self._ready)

    def _ready(self) -> None:
        text = sys.stdin.readline()
        if not text:  # EOF
            self.close()
            self._lines.put_nowait(None)
        else:
            self._lines.put_nowait(text.strip())

    async def line(self, until: asyncio.Task[Any]) -> str | None:
        """The next line, or None at EOF or once `until` finishes."""
        getting = asyncio.ensure_future(self._lines.get())
        await asyncio.wait({getting, until}, return_when=asyncio.FIRST_COMPLETED)
        if getting.done():
            return getting.result()
        getting.cancel()
        return None

    def close(self) -> None:
        self._loop.remove_reader(self._fd)


# The two modes


async def interactive(
    line: GuardedTelephony, case_id: CaseId, keyboard: Keyboard, out: Printer
) -> None:
    call_id = new_id("call")
    sid = await line.dial_agency(call_id, case_id)
    out.line(
        f"dialed (call_id={call_id} sid={sid}); type say/keys/bridge/listen/hangup"
    )

    async def watch() -> None:
        async for event in line.events():
            out.event(event)
            if isinstance(event, ListenRequested):
                # What the runner does with it, since none runs here.
                try:
                    await line.listen_in(call_id, SMOKE_USER)
                except (LineClosed, SmokeRefused) as exc:
                    out.line(f"not ringing to listen: {exc}")
            if isinstance(event, UserAnswered):
                try:
                    await line.connect_user()
                    out.line("bridged: the agency leg joined you")
                except LineClosed as exc:
                    out.line(f"not bridged: {exc}")
        out.line("the line has ended")

    watcher = asyncio.create_task(watch())
    try:
        while not watcher.done():
            command = await keyboard.line(watcher)
            if command is None or command in ("hangup", "quit"):
                break
            verb, _, rest = command.partition(" ")
            try:
                if verb == "say" and rest:
                    await line.say(rest)
                    out.line("played")
                elif verb == "keys" and rest:
                    await line.press_keys(rest)
                    out.line("keys sent; stream back")
                elif verb == "bridge":
                    await line.ring_user(call_id, SMOKE_USER)
                    out.line("ringing you; press any key when you pick up")
                elif verb == "listen":
                    out.line(f"listen-in: {request_listen_in(call_id)}")
                elif verb:
                    out.line(
                        "commands: say <text> · keys <digits> · bridge · listen · hangup"
                    )
            except (
                BlockedIdentifier,
                LineClosed,
                ValueError,
                RuntimeError,
                SmokeRefused,
            ) as exc:
                out.line(f"not sent: {exc}")
    finally:
        await line.hang_up()
        await watcher


async def with_runner(
    line: GuardedTelephony,
    case_id: CaseId,
    cases: CaseReader,
    brief_id: str,
    language: str,
    keyboard: Keyboard,
    out: Printer,
) -> None:
    clock = SystemClock()
    relay = ConsoleRelay(clock)
    job = CallJob(
        case_id=case_id,
        user_id=SMOKE_USER,
        brief_id=brief_id,
        user_language=language,
        consent_at=datetime.now(UTC),
        consent_message_id="msg_smoke",  # a dev call to our own line, not a user's
        max_hold_minutes=15,
    )
    store = FakeCallStore()
    log = FakeEventLog()
    deps = CallDeps(
        telephony=line,
        relay=relay,
        cases=cases,
        calls=store,
        events=log,
        clock=clock,
    )
    call = asyncio.create_task(run_call("job_smoke", job, deps, observer=out.step))
    asker = asyncio.create_task(_show_questions(relay, out))
    out.line(
        "runner started; type a number to answer a question, listen, end, or hangup"
    )
    try:
        while not call.done():
            command = await keyboard.line(call)
            if command is None or command in ("hangup", "quit"):
                call.cancel()
                break
            if command == "listen":
                for call_id in store.calls:
                    out.line(f"listen-in: {request_listen_in(call_id)}")
            elif command == "end":
                for call_id in store.calls:
                    out.line(f"hang-up: {request_hang_up(call_id)}")
            elif command.isdigit():
                try:
                    relay.answer(int(command))
                except ValueError as exc:
                    out.line(str(exc))
    finally:
        asker.cancel()
        try:
            report = await call
            out.line(f"report: outcome={report.outcome}")
            out.save("report", report=report.model_dump(mode="json"))
        except asyncio.CancelledError:
            out.line("cancelled; the runner wrapped up and hung up")
        for saved in store.calls.values():
            lines = [line.model_dump(mode="json") for line in saved.transcript]
            out.save("transcript", lines=lines, states=saved.states)
        out.save("events", events=[e.model_dump(mode="json") for e in log.events])


async def _show_questions(relay: ConsoleRelay, out: Printer) -> None:
    shown: str | None = None
    while True:
        question = relay.open
        if question is not None and question.request.question_id != shown:
            shown = question.request.question_id
            options = question.request.options_en
            choices = " · ".join(f"{i}) {o}" for i, o in enumerate(options, 1))
            out.line(f"question for the applicant: {choices}")
        await asyncio.sleep(0.2)


# Setup


class Server:
    """The phone routes, served in this process."""

    def __init__(self, port: int) -> None:
        app = FastAPI(title="phone smoke test")
        app.include_router(router)
        self._server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
            )
        )
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._server.serve())
        async with asyncio.timeout(_SERVER_START_S):
            while not self._server.started:
                if self._task.done():
                    self._task.result()  # raises why it failed, e.g. port in use
                await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self._server.should_exit = True
        if self._task is not None:
            await asyncio.wait({self._task}, timeout=_SERVER_START_S)


async def demo_case() -> CaseId:
    user = await reads.first_user()
    cases = await reads.list_active_cases(user.id) if user else []
    if not cases:
        raise SmokeRefused(
            "no seeded case; run `python -m app.db.reset --yes` (ask first)"
        )
    return cases[0].id


async def main(args: argparse.Namespace) -> None:
    settings = SmokeSettings()
    if missing := missing_settings(settings, args):
        sys.exit(f"missing env vars: {', '.join(missing)}")
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("twilio").setLevel(logging.WARNING)  # every request, verbatim
    pipecat_logger.remove()
    pipecat_logger.add(sys.stderr, level="WARNING")  # its debug logs carry speech

    numbers: NumberSource
    cases: CaseReader
    applicant = settings.phone_smoke_user_number if args.bridge else None
    if args.own_number:
        numbers = SmokeNumberSource(settings.phone_smoke_dial_number, applicant)
        case_id, brief_id = OWN_CASE, OWN_BRIEF
        cases = FakeCaseReader({OWN_BRIEF: demo_brief(OWN_CASE, OWN_BRIEF)})
        blocked = list(SIM_BLOCKED)
        print("WARNING: dialing your own phone (PHONE_SMOKE_DIAL_NUMBER).")
    else:
        numbers = MockLineOnly(
            DbNumberSource(), settings.twilio_mock_agency_number, applicant
        )
        case_id = args.case or await demo_case()
        brief = await reads.latest_brief(case_id)
        if brief is None and args.runner:
            raise SmokeRefused(f"case {case_id} has no brief for the runner")
        brief_id = brief.id if brief else ""
        cases = DbCaseReader()
        blocked = await load_blocked_values(case_id)

    await numbers.official_dial_number(case_id)  # refuse now, not mid-call
    server = Server(args.port)
    await server.start()
    raw = TwilioTelephony(
        numbers,
        TwilioCalls(settings),
        LineUrls.from_settings(settings),
        user_language=args.language,
        join_gate=not args.no_gate,
    )
    line = GuardedTelephony(raw, blocked)
    mode = (
        ("runner" if args.runner else "manual")
        + ("-own" if args.own_number else "")
        + ("-bridge" if args.bridge else "")
    )
    out = Printer(None if args.no_save else run_file_for(mode))
    out.save("run", mode=mode, case_id=case_id, started_at=datetime.now(UTC))
    keyboard = Keyboard()
    try:
        if args.runner:
            await with_runner(
                line, case_id, cases, brief_id, args.language, keyboard, out
            )
        else:
            await interactive(line, case_id, keyboard, out)
    finally:
        keyboard.close()
        await line.hang_up()
        await server.stop()
        out.close()


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--runner", action="store_true", help="let the call runner drive"
    )
    parser.add_argument(
        "--own-number", action="store_true", help="dial PHONE_SMOKE_DIAL_NUMBER"
    )
    parser.add_argument(
        "--case", help="a seeded case ID (default: the first user's case)"
    )
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="ring PHONE_SMOKE_USER_NUMBER as the applicant when a person answers",
    )
    parser.add_argument(
        "--language",
        choices=sorted(JOIN_PROMPTS),
        default=SMOKE_LANGUAGE,
        help="the applicant's language: the join prompt speaks it",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="join the applicant on pick-up, with no key press (PHONE_JOIN_GATE)",
    )
    parser.add_argument("--port", type=int, default=8000, help="where ngrok forwards")
    parser.add_argument(
        "--no-save", action="store_true", help="don't save the run to smoke_runs/"
    )
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except SmokeRefused as exc:
        sys.exit(f"refused: {exc}")
    except KeyboardInterrupt:
        print("\ninterrupted")


if __name__ == "__main__":
    cli()
