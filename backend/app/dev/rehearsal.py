"""A dress rehearsal on a Neon test branch, with no WhatsApp, no phone and no API
key: letter → research → consent → the phone worker's job handler on a simulated
line → report. At every stage it checks the dashboard API and, optionally,
screenshots the dashboard, then writes a report of anything that looks wrong.

    cd backend && python -m app.dev.rehearsal --out ../rehearsal

What's real and what's a stand-in:
- Real: the database helpers and contracts, the dashboard API, the phone worker's
  job handler (`handle_call_job`: the call runner, the report builder's checks, the
  `memory_write` it queues), its DB adapters, its guard and its brief validation.
- Stand-ins: research is `FakeResearch` (contract fixtures), the agency line is a
  `sim_trees` phone tree, the phone agent's model (menu, phase, report) is
  scripted, and the user's consent and answers are written directly.

Safety: it only runs against `TEST_DATABASE_URL` (refusing the shared database's
host) and rebuilds that branch's tables first. It never dials: the line is fake.
It writes several owners' tables, which is why it lives in `app/dev/`.

Screenshots need the dashboard pointed at this branch, e.g. the backend on :8001
with `DATABASE_URL_UNPOOLED=<TEST_DATABASE_URL>` and the dashboard on :3001 with
`BACKEND_URL=http://localhost:8001 NEXT_PUBLIC_DATA=live`.
"""

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from app.contracts import (
    CallJob,
    CallReport,
    Component,
    Event,
    EventType,
    JobType,
    MessageDirection,
    MessageSender,
    ResearchFastJob,
)
from app.contracts.common import CallState
from app.db import jobs, reads, tables
from app.db.events import append_event
from app.db.ids import new_id
from app.db.messages import append_message
from app.db.tables import utcnow
from app.db.writes import orchestrator
from app.dev.fake_research import FakeResearch, Pacing
from app.phone.adapters import DbCallStore, DbNumberSource
from app.phone.clock import SystemClock
from app.phone.fakes import Answer, FakeRelay, FakeTelephony
from app.phone.menu import (
    MenuAction,
    MenuDecision,
    PressAction,
    SayAction,
    WaitAction,
)
from app.phone.phase import PhaseJudgment
from app.phone.report import ReportDraft
from app.phone.runner import RunnerConfig
from app.phone.sim_line import Hold, PhoneTree
from app.phone.sim_trees import TREES
from app.phone.worker import PhoneDeps, handle_call_job
from app.settings import Settings, get_settings, to_asyncpg_url

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[3]
LETTER = (
    REPO / "backend/tests/fixtures/research/letters/i797c_asylum_interview/page_1.png"
)
USER_NUMBER = "+15555550142"
"""A made-up number for the rehearsal user; nothing is sent or dialed."""
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


# The runner's model, scripted for the `speech_federal` tree


def _phase(heard: str) -> tuple[str, float]:
    text = heard.lower()
    if ("my name is" in text or "this is" in text) and "?" in text:
        return "human", 0.92
    if "hold" in text or "wait" in text or "caller number" in text:
        return "hold", 0.9
    return "menu", 0.9


def _menu(heard: str) -> MenuAction:
    text = heard.lower()
    if "for english, press 1" in text:
        return PressAction(
            kind="press", digits="1", option_label_en="English", reason_en="language"
        )
    if "briefly tell me" in text:
        return SayAction(
            kind="say", text="appointments and interviews", reason_en="the goal"
        )
    if "already scheduled, press 2" in text:
        return PressAction(
            kind="press", digits="2", option_label_en="interview", reason_en="goal"
        )
    return WaitAction(kind="wait", reason_en="listening")


REPORT_DRAFT = ReportDraft(
    summary_en="A representative answered and the applicant joined the call.",
    outcome="partial",
    reference_number=None,
    rep_name=None,
    next_steps_en=["Bring the interview notice and your passport to the interview"],
    new_deadlines=[],
    proposed_facts=["The applicant spoke with USCIS about the asylum interview"],
    followup_needed=True,
)


class ScriptedLlm:
    """Stands in for Claude in the phone worker: phase and menu choice from what was
    heard, and a fixed call report."""

    def __init__(
        self,
        menu: Callable[[str], MenuAction] = _menu,
        phase: Callable[[str], tuple[str, float]] = _phase,
    ) -> None:
        self._menu = menu
        self._phase = phase

    async def parse(
        self, *, system: str, user: str, output_type: type, timeout_s: float
    ) -> Any:
        if output_type is ReportDraft:
            return REPORT_DRAFT
        heard = user.rsplit("\n", 1)[-1].strip().strip('"')
        if output_type is PhaseJudgment:
            phase, confidence = self._phase(heard)
            return PhaseJudgment(phase=phase, confidence=confidence, reason_en="cues")
        return MenuDecision(action=self._menu(heard))


# The dashboard, seen from outside


class Browser:
    """One headless Edge over the DevTools protocol, kept open between shots."""

    def __init__(self, path: str, out: Path, width: int = 1920, height: int = 1080):
        self._path = path
        self._out = out
        self._size = (width, height)
        self._proc: asyncio.subprocess.Process | None = None
        self._ws: Any = None
        self._n = 0

    async def __aenter__(self) -> Self:
        import websockets

        profile = tempfile.mkdtemp(prefix="rehearsal-edge-")
        self._proc = await asyncio.create_subprocess_exec(
            self._path,
            "--headless=new",
            "--remote-debugging-port=9334",
            f"--user-data-dir={profile}",
            "about:blank",
        )
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    tabs = (await client.get("http://127.0.0.1:9334/json")).json()
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.2)
            else:
                raise RuntimeError("headless Edge didn't start")
        url = next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"]
        self._ws = await websockets.connect(url, max_size=None)
        width, height = self._size
        await self._call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=False,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._proc is not None:
            self._proc.kill()

    async def _call(self, method: str, **params: Any) -> dict[str, Any]:
        """One DevTools call; a browser that stops answering fails the run."""
        return await asyncio.wait_for(self._call_once(method, **params), 30)

    async def _call_once(self, method: str, **params: Any) -> dict[str, Any]:
        self._n += 1
        await self._ws.send(
            json.dumps({"id": self._n, "method": method, "params": params})
        )
        while True:
            message = json.loads(await self._ws.recv())
            if message.get("id") == self._n:
                return message.get("result", {})

    async def open(self, url: str) -> None:
        await self._call("Page.navigate", url=url)

    async def shot(self, name: str, settle_s: float = 2.5) -> Path:
        import base64

        await asyncio.sleep(settle_s)  # the page polls every 1-3 s
        data = await self._call("Page.captureScreenshot", format="png")
        path = self._out / f"{name}.png"
        path.write_bytes(base64.b64decode(data["data"]))
        return path


@dataclasses.dataclass
class Stage:
    name: str
    expected: str
    seen: str | None = None
    screenshot: str | None = None
    problems: list[str] = dataclasses.field(default_factory=list)


class Rehearsal:
    def __init__(self, api: str, dashboard: str, browser: Browser | None) -> None:
        self.api = api.rstrip("/")
        self.dashboard = dashboard.rstrip("/")
        self.browser = browser
        self.stages: list[Stage] = []
        self.user: tables.User | None = None
        self.case_id = ""
        self.started = time.monotonic()

    async def check(self, name: str, expected: str) -> Stage:
        """Read the case and the feed through the dashboard API, as the page does."""
        stage = Stage(name, expected)
        async with httpx.AsyncClient(base_url=self.api, timeout=20) as client:
            case = await client.get(f"/api/cases/{self.case_id}", params={"lang": "es"})
            if case.status_code != 200:
                stage.problems.append(f"GET /api/cases → {case.status_code}")
            else:
                stage.seen = case.json()["stage"]
                if stage.seen != expected:
                    stage.problems.append(f"stage is {stage.seen}, expected {expected}")
            assert self.user is not None
            feed = await client.get(
                f"/api/users/{self.user.id}/feed", params={"lang": "es"}
            )
            for item in feed.json() if feed.status_code == 200 else []:
                text = item["text"]
                if text["text"] == text["en"]:
                    stage.problems.append(
                        f"feed line not in Spanish ({item['type']}): {text['en']!r}"
                    )
        if self.browser is not None:
            stage.screenshot = (
                await self.browser.shot(f"{len(self.stages):02d}-{name}")
            ).name
        self.stages.append(stage)
        logger.info("Stage %s: %s %s", name, stage.seen, stage.problems or "")
        return stage

    async def run(self, tree_name: str) -> CallReport:
        await self._letter()
        await self._research()
        job = await self._consent()
        return await self._call(job, tree_name)

    async def _letter(self) -> None:
        user = await orchestrator.get_or_create_user(USER_NUMBER)
        self.user = await orchestrator.set_language(user.id, "es")
        media = await orchestrator.save_media(
            self.user.id, "image/png", LETTER.read_bytes()
        )
        await append_message(
            self.user.id,
            MessageDirection.IN,
            MessageSender.USER,
            "",
            "es",
            media_ids=[media.id],
        )
        document = await orchestrator.create_document(self.user.id, [media.id])
        self.case_id = new_id("case")
        await jobs.enqueue(
            ResearchFastJob(
                case_id=self.case_id,
                user_id=self.user.id,
                document_ids=[document.id],
                user_language="es",
            ),
            Component.ORCHESTRATOR,
            self.user.id,
            self.case_id,
        )
        if self.browser is not None:
            await self.browser.open(
                f"{self.dashboard}/u/{self.user.id}/cases/{self.case_id}"
            )

    async def _research(self) -> None:
        settings = get_settings()
        research = FakeResearch(
            settings.twilio_mock_agency_number or "+15672298566",
            Pacing(fast_s=2.0, deep_s=4.0, poll_s=0.3),
        )
        research.start(run_for_s=60)
        await self._until_stage("checking")
        await self.check("explained", "checking")
        await self._until_stage("verified")
        await self.check("verified", "verified")

    async def _consent(self) -> tables.Job:
        """What the orchestrator's consent gate writes, minus WhatsApp: the request,
        the user's own YES, then the call job pointing at that message (rule 4)."""
        assert self.user is not None
        await self._event(
            EventType.CONSENT_REQUESTED, Component.ORCHESTRATOR, agency="USCIS"
        )
        yes = await append_message(
            self.user.id,
            MessageDirection.IN,
            MessageSender.USER,
            "1",
            "es",
            body_en="1",
        )
        await self._event(EventType.CONSENT_GIVEN, Component.ORCHESTRATOR)
        brief = await reads.latest_brief(self.case_id)
        if brief is None:
            raise RuntimeError("research left no brief")
        await jobs.enqueue(
            CallJob(
                case_id=self.case_id,
                user_id=self.user.id,
                brief_id=brief.id,
                user_language="es",
                consent_at=utcnow(),
                consent_message_id=yes.id,
                max_hold_minutes=5,
            ),
            Component.ORCHESTRATOR,
            self.user.id,
            self.case_id,
        )
        job = await jobs.claim_next(JobType.CALL)
        if job is None:
            raise RuntimeError("the call job wasn't claimable")
        return job

    async def _call(self, job: tables.Job, tree_name: str) -> CallReport:
        rehearsal = self
        tree = TREES[tree_name]
        # Short holds, so the run takes a minute or two of real time.
        nodes = {
            name: dataclasses.replace(node, music_s=4.0)
            if isinstance(node, Hold)
            else node
            for name, node in tree.nodes.items()
        }
        tree = dataclasses.replace(tree, nodes=nodes)
        clock = SystemClock()
        phone = PhoneTree(tree, clock)
        line = FakeTelephony(DbNumberSource(), clock, responder=phone)
        phone.attach(line)

        class Watched(DbCallStore):
            async def set_state(
                self, call_id: str, state: CallState, twilio_call_sid: str | None = None
            ) -> None:
                await super().set_state(call_id, state, twilio_call_sid)
                expected = {
                    CallState.DIALING: "calling",
                    CallState.MENU: "calling",
                    CallState.HOLD: "on_hold",
                    CallState.HUMAN_DETECTED: "connected",
                    CallState.BRIDGING: "connected",
                    CallState.CONNECTED: "connected",
                    CallState.WRAP_UP: "call_ended",
                    CallState.ENDED: "call_ended",
                }[CallState(state)]
                await rehearsal.check(f"call-{state}", expected)

        # The phone worker's own job handler, with the line and the model faked.
        llm = ScriptedLlm()
        deps = PhoneDeps(
            line_factory=lambda _job: line,
            menu_llm=llm,
            report_llm=llm,
            relay=FakeRelay(clock, [Answer(1, after_s=1.0)]),
            calls=Watched(),
            clock=clock,
            config=RunnerConfig(hold_limit_s=120),
        )
        report = await handle_call_job(job, deps)
        if report is None:
            failed = await reads.get_job(job.id)
            raise RuntimeError(f"the call job failed: {failed and failed.error}")
        await self._after_call(report)
        return report

    async def _after_call(self, report: CallReport) -> None:
        """The report on the dashboard, and the call's facts queued for memory."""
        stage = await self.check("report", "call_ended")
        async with httpx.AsyncClient(base_url=self.api, timeout=20) as client:
            response = await client.get(
                f"/api/cases/{self.case_id}", params={"lang": "es"}
            )
        calls = (response.json().get("calls") or []) if response.is_success else []
        shown = (calls[-1].get("report") if calls else None) or {}
        if not shown.get("summary"):
            stage.problems.append("the call report has no summary on the dashboard")
        if len(shown.get("next_steps") or []) != len(report.next_steps_en):
            stage.problems.append("the dashboard doesn't show every next step")
        memory = await jobs.claim_next(JobType.MEMORY_WRITE)
        if memory is None or memory.payload.get("source_ref") != report.call_id:
            stage.problems.append("the call's facts weren't queued as memory_write")

    async def _until_stage(self, stage: str, timeout_s: float = 60) -> None:
        """Wait on the case's stage, as the dashboard does."""
        deadline = time.monotonic() + timeout_s
        seen = None
        while time.monotonic() < deadline:
            if await reads.get_case(self.case_id) is not None:
                seen = str(await reads.case_progress(self.case_id))
                if seen == stage:
                    return
            await asyncio.sleep(0.3)
        raise TimeoutError(f"case never reached {stage} (last: {seen})")

    async def _event(
        self, event_type: EventType, source: Component, **data: Any
    ) -> None:
        assert self.user is not None
        await append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=event_type,
                source=source,
                user_id=self.user.id,
                case_id=self.case_id,
                summary_en=str(event_type),
                data=data,
            )
        )


def write_report(
    out: Path, rehearsal: Rehearsal, report: CallReport | None, error: str | None
) -> Path:
    lines = [
        "# Rehearsal report",
        "",
        (
            f"Run at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, "
            f"{time.monotonic() - rehearsal.started:.0f} s. Case `{rehearsal.case_id}`."
        ),
        "",
    ]
    if error:
        lines += [f"**The run stopped:** {error}", ""]
    if report is not None:
        lines += [
            (
                f"Call outcome: `{report.outcome}`; summary: {report.summary_en or '(none)'}; "
                f"next steps: {report.next_steps_en or '(none)'}; "
                f"transcript `{report.transcript_id}`."
            ),
            "",
        ]
    problems = sum(len(s.problems) for s in rehearsal.stages)
    lines += [
        f"{len(rehearsal.stages)} checks, {problems} problems.",
        "",
        "| # | Stage | Expected | Dashboard API says | Screenshot | Problems |",
        "|---|---|---|---|---|---|",
    ]
    for i, stage in enumerate(rehearsal.stages):
        shot = f"[{stage.screenshot}]({stage.screenshot})" if stage.screenshot else ""
        issues = "<br>".join(dict.fromkeys(stage.problems)) or "none"
        lines.append(
            f"| {i} | {stage.name} | {stage.expected} | {stage.seen} | {shot} | {issues} |"
        )
    path = out / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def use_test_branch() -> None:
    """Point every helper at TEST_DATABASE_URL, refusing the shared database."""
    settings = Settings()
    test_url = settings.test_database_url
    if not test_url:
        raise SystemExit("Set TEST_DATABASE_URL to your own Neon branch first.")
    shared = urlsplit(settings.async_database_url).hostname
    if urlsplit(to_asyncpg_url(test_url)).hostname == shared:
        raise SystemExit("TEST_DATABASE_URL points at the shared database; refusing.")
    os.environ["DATABASE_URL_UNPOOLED"] = test_url
    get_settings.cache_clear()


async def main_async(args: argparse.Namespace) -> int:
    from app.db.engine import get_engine
    from app.db.schema import create_all, drop_all

    use_test_branch()
    get_engine.cache_clear()
    print(f"Rehearsing on {urlsplit(get_settings().async_database_url).hostname}")
    await drop_all()
    await create_all()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: CallReport | None = None
    error: str | None = None
    browser = None if args.no_screens else Browser(args.browser, out)
    rehearsal = Rehearsal(args.api, args.dashboard, browser)
    try:
        if browser is not None:
            await browser.__aenter__()
        try:
            report = await rehearsal.run(args.tree)
        except Exception as exc:
            logger.exception("Rehearsal stopped")
            error = f"{type(exc).__name__}: {exc}"
    finally:
        if browser is not None:
            await browser.__aexit__()
    path = write_report(out, rehearsal, report, error)
    print(f"Report: {path}")
    problems = sum(len(s.problems) for s in rehearsal.stages)
    return 1 if error or problems else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.dev.rehearsal")
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--dashboard", default="http://localhost:3001")
    parser.add_argument("--out", default=str(REPO / "rehearsal"))
    parser.add_argument("--tree", default="speech_federal", choices=sorted(TREES))
    parser.add_argument("--browser", default=os.environ.get("REHEARSAL_BROWSER", EDGE))
    parser.add_argument("--no-screens", action="store_true", help="API checks only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
