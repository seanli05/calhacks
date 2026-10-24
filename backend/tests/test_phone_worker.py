"""The phone worker on fakes: a claimed `call` job runs a whole call and ends
`done` with its P3 report and a `memory_write` job, or `failed` when there's no
report. No database: the job helpers are swapped for an in-memory fake, like the
research tests' `FakeResearchDB`.
"""

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

import pytest
from app.contracts import (
    CallJob,
    CallOutcome,
    CallReport,
    EventType,
    FactSource,
    JobStatus,
    JobType,
    MemoryWriteJob,
    ResearchDeepJob,
)
from app.contracts.common import CallId, JobId
from app.contracts.jobs import JobPayload
from app.db import tables
from app.phone import worker
from app.phone.fakes import (
    Action,
    ConnectedUser,
    FakeCallStore,
    FakeCaseReader,
    FakeClock,
    FakeEventLog,
    FakeNumberSource,
    FakeRelay,
    FakeTelephony,
    RangUser,
    Said,
    Step,
)
from app.phone.line import AgencyAnswered, AgencyHungUp, Heard, NonSpeech, UserAnswered
from app.phone.llm import LlmError
from app.phone.menu import MenuDecision, PressAction, WaitAction
from app.phone.phase import PhaseJudgment
from app.phone.report import ReportDraft
from app.phone.twilio_line import TwilioTelephony
from app.phone.worker import (
    PhoneDeps,
    PhoneWorker,
    handle_call_job,
    missing_settings,
    twilio_lines,
)
from app.settings import Settings
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

OFFICIAL = "+18005550100"
A_NUMBER = "A201234567"
BRIEF = {
    "brief_id": "brief_77",
    "case_id": "case_123",
    "call_goal_en": "Confirm the asylum interview is still scheduled",
}
MENU = "For appointments, press 2. For anything else, press 3."
REP = "Thank you for holding, this is Maria, how can I help you?"


def _call_job() -> CallJob:
    return CallJob(
        case_id="case_123",
        user_id="user_9",
        brief_id="brief_77",
        user_language="es",
        consent_at=datetime(2026, 10, 25, 10, 2, tzinfo=UTC),
        consent_message_id="msg_41",
        max_hold_minutes=60,
    )


class FakeJobs:
    """`app.db.jobs`' writes, in memory."""

    def __init__(self) -> None:
        self.jobs: dict[JobId, tables.Job] = {}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakeJobs":
        for name in ("enqueue", "finish", "fail"):
            monkeypatch.setattr(f"app.db.jobs.{name}", getattr(self, name))
        return self

    def add_claimed(self, payload: JobPayload | dict[str, Any]) -> tables.Job:
        """A job as `claim_next` returns it: already running."""
        dumped = (
            payload if isinstance(payload, dict) else payload.model_dump(mode="json")
        )
        job = tables.Job(
            type=JobType.CALL,
            status=JobStatus.RUNNING,
            created_by="orchestrator",
            user_id="user_9",
            case_id="case_123",
            payload=dumped,
        )
        self.jobs[job.id] = job
        return job

    def of_type(self, job_type: JobType) -> list[tables.Job]:
        return [job for job in self.jobs.values() if job.type == job_type]

    async def enqueue(
        self,
        payload: JobPayload,
        created_by: str,
        user_id: str,
        case_id: str | None = None,
    ) -> tables.Job:
        job = tables.Job(
            type=JobType(payload.job),
            created_by=created_by,
            user_id=user_id,
            case_id=case_id,
            payload=payload.model_dump(mode="json"),
        )
        self.jobs[job.id] = job
        return job

    async def finish(self, job_id: JobId, result: BaseModel | dict) -> tables.Job:
        job = self.jobs[job_id]
        job.status = JobStatus.DONE
        job.result = (
            result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        )
        return job

    async def fail(self, job_id: JobId, error: str) -> tables.Job:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error = error
        return job


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeJobs:
    return FakeJobs().install(monkeypatch)


# A fake Claude for the whole call: phase (1c), menu (1b), and the report.


def _phase(heard: str) -> tuple[str, float]:
    text = heard.lower()
    if "press" in text:
        return "menu", 0.95
    if "this is" in text and "?" in text:
        return "human", 0.92
    if "hold" in text:
        return "hold", 0.9
    return "unclear", 0.3


GOOD_DRAFT = ReportDraft(
    summary_en="Maria confirmed the interview and gave a reference number.",
    outcome="resolved",
    reference_number="R-55821",
    rep_name="Maria",
    next_steps_en=["The interview is still on for November 18"],
    new_deadlines=[],
    proposed_facts=["Asylum interview confirmed for November 18, 2026"],
    followup_needed=False,
)


class FakeLlm:
    def __init__(self, report: ReportDraft | Exception = GOOD_DRAFT) -> None:
        self.report = report
        self.report_calls = 0

    async def parse(
        self, *, system: str, user: str, output_type: type, timeout_s: float
    ) -> Any:
        if output_type is ReportDraft:
            self.report_calls += 1
            if isinstance(self.report, Exception):
                raise self.report
            return self.report
        heard = user.rsplit("\n", 1)[-1].strip().strip('"')
        if output_type is PhaseJudgment:
            phase, confidence = _phase(heard)
            return PhaseJudgment(phase=phase, confidence=confidence, reason_en="cues")
        if "press 2" in heard.lower():
            action = PressAction(
                kind="press", digits="2", option_label_en="appointments", reason_en="t"
            )
        else:
            action = WaitAction(kind="wait", reason_en="t")
        return MenuDecision(action=action)


def _tree(action: Action) -> list[Step]:
    """Press 2, hold, Maria picks up; the applicant joins and she gives a
    reference number, then hangs up."""
    if action == Said("two"):
        return [
            Step(1, NonSpeech(sound="music", seconds=30)),
            Step(30, Heard(text="Please continue to hold.")),
            Step(60, Heard(text=REP)),
        ]
    if isinstance(action, RangUser):
        return [Step(8, UserAnswered())]
    if isinstance(action, ConnectedUser):
        return [
            Step(60, Heard(text="The interview is still on for November 18th.")),
            Step(20, Heard(text="Your reference number is R-55821.")),
            Step(20, AgencyHungUp()),
        ]
    return []


class Setup:
    """One worker's fakes. `lines` keeps every line the factory made."""

    def __init__(
        self,
        *,
        verified: bool = True,
        llm: FakeLlm | None = None,
        calls: FakeCallStore | None = None,
        script: Iterable[Step] | None = None,
    ) -> None:
        self.clock = FakeClock()
        self.store = calls or FakeCallStore()
        self.log = FakeEventLog()
        self.llm = llm or FakeLlm()
        self.numbers = FakeNumberSource(
            verified={"case_123": OFFICIAL} if verified else {},
            users={"user_9": "+15555550123"},
        )
        self.script = (
            [Step(2, AgencyAnswered()), Step(1, Heard(text=MENU))]
            if script is None
            else list(script)
        )
        self.lines: list[FakeTelephony] = []
        self.blocked_for: list[str] = []

    def line(self, job: CallJob) -> FakeTelephony:
        line = FakeTelephony(self.numbers, self.clock, self.script, _tree)
        self.lines.append(line)
        return line

    async def blocked(self, case_id: str) -> list[str]:
        self.blocked_for.append(case_id)
        return [A_NUMBER]

    def deps(self) -> PhoneDeps:
        return PhoneDeps(
            line_factory=self.line,
            menu_llm=self.llm,
            report_llm=self.llm,
            relay=FakeRelay(self.clock, []),
            cases=FakeCaseReader({"brief_77": BRIEF}),
            calls=self.store,
            events=self.log,
            clock=self.clock,
            blocked_values=self.blocked,
        )

    @property
    def call(self):
        [call] = self.store.calls.values()
        return call


async def test_happy_path_finishes_the_job_and_queues_memory(db: FakeJobs) -> None:
    setup = Setup()
    job = db.add_claimed(_call_job())

    report = await setup.clock.run(handle_call_job(job, setup.deps()))

    assert report is not None
    assert report.outcome == CallOutcome.RESOLVED
    assert report.reference_number == "R-55821"
    assert report.rep_name == "Maria"
    assert setup.llm.report_calls == 1

    # The job is done with the report as its result (P3, C13).
    assert job.status == JobStatus.DONE
    assert CallReport.model_validate(job.result) == report

    # The runner made the call row (C7) from the job's consent (rule 4) and saved
    # the report and transcript on it (C12).
    call = setup.call
    assert call.job_id == job.id
    assert call.job.consent_message_id == "msg_41"
    assert call.report == report
    assert report.transcript_id == call.transcript_id
    assert setup.blocked_for == ["case_123"]
    assert EventType.CALL_ENDED in setup.log.types

    # The facts go to the memory writer, from this call.
    [memory] = db.of_type(JobType.MEMORY_WRITE)
    payload = MemoryWriteJob.model_validate(memory.payload)
    assert payload.source == FactSource.FROM_CALL
    assert payload.source_ref == report.call_id
    assert payload.proposed_facts == report.proposed_facts
    assert memory.created_by == "phone_agent"
    assert memory.case_id == "case_123"


async def test_unverified_case_is_done_with_a_failed_report(db: FakeJobs) -> None:
    setup = Setup(verified=False)
    job = db.add_claimed(_call_job())

    report = await setup.clock.run(handle_call_job(job, setup.deps()))

    assert report is not None and report.outcome == CallOutcome.FAILED
    assert job.status == JobStatus.DONE
    assert setup.llm.report_calls == 0
    assert db.of_type(JobType.MEMORY_WRITE) == []


async def test_report_failure_still_finishes_with_the_fallback(db: FakeJobs) -> None:
    setup = Setup(llm=FakeLlm(report=LlmError("timed out after 45.0s")))
    job = db.add_claimed(_call_job())

    report = await setup.clock.run(handle_call_job(job, setup.deps()))

    assert report is not None and report.outcome == CallOutcome.PARTIAL
    assert report.followup_needed and report.proposed_facts == []
    assert job.status == JobStatus.DONE
    assert db.of_type(JobType.MEMORY_WRITE) == []


class BrokenCallStore(FakeCallStore):
    async def create_call(self, job_id: JobId, job: CallJob) -> CallId:
        raise OperationalError("insert", {}, ConnectionError("db down"))


async def test_call_that_cant_be_created_fails_the_job(db: FakeJobs) -> None:
    setup = Setup(calls=BrokenCallStore())
    job = db.add_claimed(_call_job())

    report = await setup.clock.run(handle_call_job(job, setup.deps()))

    assert report is None
    assert job.status == JobStatus.FAILED
    assert job.error == "OperationalError"
    assert setup.lines[0].actions == []  # never dialed
    assert db.of_type(JobType.MEMORY_WRITE) == []


@pytest.mark.parametrize(
    "payload",
    [
        ResearchDeepJob(case_id="case_123", user_id="user_9", document_ids=["doc_1"]),
        {"job": "call", "case_id": "case_123"},
    ],
    ids=["wrong type", "invalid"],
)
async def test_bad_payload_fails_the_job_without_a_call(
    db: FakeJobs, payload: JobPayload | dict[str, Any]
) -> None:
    setup = Setup()
    job = db.add_claimed(payload)

    assert await handle_call_job(job, setup.deps()) is None
    assert job.status == JobStatus.FAILED
    assert setup.lines == [] and setup.store.calls == {}


async def test_memory_queue_failure_keeps_the_job_done(
    db: FakeJobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enqueue(*_: Any, **__: Any) -> None:
        raise OperationalError("insert", {}, ConnectionError("db down"))

    monkeypatch.setattr("app.db.jobs.enqueue", enqueue)
    setup = Setup()
    job = db.add_claimed(_call_job())

    report = await setup.clock.run(handle_call_job(job, setup.deps()))

    assert report is not None
    assert job.status == JobStatus.DONE


async def test_worker_claims_calls_and_survives_a_failed_claim(
    db: FakeJobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = [db.add_claimed(_call_job()), db.add_claimed(_call_job())]
    claims: list[Callable[[], tables.Job | None]] = [
        lambda: jobs[0],
        _raise_db_error,
        lambda: jobs[1],
    ]
    handled: list[str] = []
    done = asyncio.Event()

    async def claim_next(job_type: JobType) -> tables.Job | None:
        assert job_type == JobType.CALL
        return claims.pop(0)() if claims else None

    async def handle(job: tables.Job, _: PhoneDeps) -> None:
        handled.append(job.id)
        if len(handled) == 1:
            raise RuntimeError("one bad call")
        done.set()

    monkeypatch.setattr("app.db.jobs.claim_next", claim_next)
    monkeypatch.setattr(worker, "handle_call_job", handle)

    phone_worker = PhoneWorker(Setup().deps(), poll_s=0.01)
    phone_worker.start()
    await asyncio.wait_for(done.wait(), 1)
    await phone_worker.stop()

    assert handled == [jobs[0].id, jobs[1].id]


def _raise_db_error() -> tables.Job | None:
    raise OperationalError("select", {}, ConnectionError("db down"))


# Wiring into the app


def _live_settings(**overrides: str) -> Settings:
    values = {
        "anthropic_api_key": "fake",
        "twilio_account_sid": "ACfake",
        "twilio_auth_token": "fake",
        "twilio_agent_number": "+15555550100",
        "cartesia_api_key": "fake",
        "cartesia_agent_voice_id": "voice_fake",
        "public_base_url": "https://agent.example.test",
    }
    return Settings(_env_file=None, **(values | overrides))  # type: ignore[call-arg]


def test_missing_settings_names_each_env_var() -> None:
    assert missing_settings(_live_settings()) == []
    missing = missing_settings(_live_settings(public_base_url="", twilio_auth_token=""))
    assert missing == ["TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL"]


def test_phone_worker_is_off_by_default() -> None:
    """Only the deployed backend claims jobs on the shared database."""
    assert Settings(_env_file=None).phone_worker is False  # type: ignore[call-arg]


def test_twilio_lines_makes_a_fresh_line_per_call_in_the_jobs_language() -> None:
    lines = twilio_lines(_live_settings())
    first, second = lines(_call_job()), lines(_call_job())

    assert isinstance(first, TwilioTelephony)
    assert first is not second
    assert first._user_language == "es"
