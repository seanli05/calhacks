"""Phone worker: claims `call` jobs (H2) and runs each call in its own task.

One background loop polls `jobs.claim_next` about once a second, like the research
worker. Per job: build the call's `CallDeps` (the line wrapped in
`GuardedTelephony` with the case's identifier values, C35), run the call, then
`finish` the job with the P3 report and queue a `memory_write` job for its
proposed facts. The runner creates the `calls` row and its `call_id` (C7) through
`CallStore.create_call`, and every `calls`/`transcripts` write goes through the
phone agent's adapters to `app.db.writes.phone`.

A call that ended badly (no answer, hold timeout, applicant unreachable) still has
a report, so its job is `done` with that outcome. A job is `failed` only when
there's no report: the payload didn't parse, or the call couldn't be created or
its report saved.

`main.py` starts it when `PHONE_WORKER` is true and the live-call settings are
set (`missing_settings`). Only the deployed backend runs it on the shared database,
and never beside the dev fake phone, which claims the same jobs.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

from app.contracts import (
    CallJob,
    CallReport,
    Component,
    FactSource,
    JobType,
    MemoryWriteJob,
)
from app.contracts.common import CaseId
from app.db import jobs, tables
from app.phone.adapters import (
    DbCallStore,
    DbCaseReader,
    DbEventLog,
    DbNumberSource,
    RelayAskUser,
    load_blocked_values,
)
from app.phone.clock import SystemClock
from app.phone.guard import GuardedTelephony
from app.phone.llm import AnthropicLlmClient, LlmClient
from app.phone.ports import (
    CallDeps,
    CallStore,
    CaseReader,
    Clock,
    EventLog,
    Relay,
    Telephony,
)
from app.phone.report import LlmReportBuilder
from app.phone.report_llm import AnthropicReportClient
from app.phone.runner import RunnerConfig, run_call
from app.phone.twilio_line import TwilioTelephony
from app.phone.twilio_rest import TwilioCalls
from app.phone.twilio_urls import LineUrls
from app.settings import Settings

logger = logging.getLogger(__name__)

POLL_S = 1.0

type LineFactory = Callable[[CallJob], Telephony]
"""A new, undialed line for one call. The worker wraps it in `GuardedTelephony`."""
type BlockedValues = Callable[[CaseId], Awaitable[list[str]]]

LIVE_CALL_SETTINGS = (
    "anthropic_api_key",
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_agent_number",
    "cartesia_api_key",
    "cartesia_agent_voice_id",
    "public_base_url",
)


def missing_settings(settings: Settings) -> list[str]:
    """The env vars a real call needs that aren't set."""
    return [name.upper() for name in LIVE_CALL_SETTINGS if not getattr(settings, name)]


@dataclass
class PhoneDeps:
    """Everything the worker calls out to. Defaults are the real adapters; tests
    swap in the fakes from `fakes.py`."""

    line_factory: LineFactory
    menu_llm: LlmClient
    report_llm: LlmClient
    relay: Relay = field(default_factory=RelayAskUser)
    cases: CaseReader = field(default_factory=DbCaseReader)
    calls: CallStore = field(default_factory=DbCallStore)
    events: EventLog = field(default_factory=DbEventLog)
    clock: Clock = field(default_factory=SystemClock)
    blocked_values: BlockedValues = load_blocked_values
    config: RunnerConfig | None = None


async def handle_call_job(job: tables.Job, deps: PhoneDeps) -> CallReport | None:
    """Run one claimed `call` job to `done` or `failed`. Returns the report, or
    None if the job failed."""
    try:
        payload = jobs.payload_of(job)
        if not isinstance(payload, CallJob):
            raise TypeError(f"not a call job: {payload.job}")
        blocked = await deps.blocked_values(payload.case_id)
        call_deps = CallDeps(
            telephony=GuardedTelephony(deps.line_factory(payload), blocked),
            relay=deps.relay,
            cases=deps.cases,
            calls=deps.calls,
            events=deps.events,
            clock=deps.clock,
        )
        report = await run_call(
            job.id,
            payload,
            call_deps,
            llm=deps.menu_llm,
            config=deps.config,
            report_builder=LlmReportBuilder(deps.report_llm, blocked_values=blocked),
        )
    except Exception as exc:
        logger.exception("Call job failed case_id=%s job_id=%s", job.case_id, job.id)
        # The type name only: an exception's text could carry call content.
        await jobs.fail(job.id, type(exc).__name__)
        return None

    await jobs.finish(job.id, report)
    if report.proposed_facts:
        await _queue_memory_write(job, payload, report)
    return report


async def _queue_memory_write(
    job: tables.Job, payload: CallJob, report: CallReport
) -> None:
    """The memory writer holds the facts (all sensitive) until the applicant
    agrees (C15). A failure here loses only the proposed facts, not the call: the
    report is already saved and the job done."""
    try:
        await jobs.enqueue(
            MemoryWriteJob(
                user_id=payload.user_id,
                source=FactSource.FROM_CALL,
                source_ref=report.call_id,
                proposed_facts=report.proposed_facts,
            ),
            Component.PHONE_AGENT,
            payload.user_id,
            payload.case_id,
        )
    except (SQLAlchemyError, OSError):
        logger.exception(
            "Queueing memory_write failed case_id=%s call_id=%s job_id=%s",
            payload.case_id,
            report.call_id,
            job.id,
        )


class PhoneWorker:
    def __init__(self, deps: PhoneDeps, poll_s: float = POLL_S) -> None:
        self.deps = deps
        self._poll_s = poll_s
        self._loop: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        if self._loop is None or self._loop.done():
            self._loop = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop polling and cancel calls still running: each hangs up and saves a
        failed report, but its job stays `running` in the DB."""
        tasks = [t for t in (self._loop, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self) -> None:
        logger.info("Phone worker started")
        while True:
            try:
                job = await jobs.claim_next(JobType.CALL)
            except (SQLAlchemyError, OSError):
                logger.exception("Phone worker: claiming a call job failed")
                job = None
            if job is None:
                await asyncio.sleep(self._poll_s)
                continue
            self._spawn(job)

    def _spawn(self, job: tables.Job) -> None:
        # The loop holds tasks weakly; keep a reference until each one finishes.
        task = asyncio.create_task(self._handle(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, job: tables.Job) -> None:
        # `handle_call_job` fails its own job; this catch only keeps an error in
        # `finish` (the DB) from reaching the loop.
        try:
            await handle_call_job(job, self.deps)
        except Exception:
            logger.exception(
                "Call job handling failed case_id=%s job_id=%s", job.case_id, job.id
            )


def twilio_lines(settings: Settings) -> LineFactory:
    """A new Twilio line per call. It dials only `official_dial_number` (rule 2,
    with C40's demo swap inside it), and its join gate speaks the job's language
    (no gate when `PHONE_JOIN_GATE=false`)."""
    numbers = DbNumberSource()
    calls = TwilioCalls(settings)
    urls = LineUrls.from_settings(settings)

    def line(job: CallJob) -> Telephony:
        return TwilioTelephony(
            numbers,
            calls,
            urls,
            user_language=job.user_language,
            join_gate=settings.phone_join_gate,
        )

    return line


def real_deps(settings: Settings) -> PhoneDeps:
    """The live clients and DB adapters around real Twilio lines. Check
    `missing_settings` first; `close_deps` closes them on shutdown."""
    return PhoneDeps(
        line_factory=twilio_lines(settings),
        menu_llm=AnthropicLlmClient(),
        report_llm=AnthropicReportClient(),
    )


async def close_deps(deps: PhoneDeps) -> None:
    if isinstance(deps.report_llm, AnthropicReportClient):
        await deps.report_llm.close()
