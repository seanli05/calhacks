"""Job handlers: the only research code that touches the Store.

Each handler takes a `jobs` row, reads what it needs, runs one pass, writes the
tables research owns (`cases`, `case_refs`, `verifications`, `case_briefs`),
queues follow-up jobs, and logs events. Passes come in through `ResearchDeps`
so tests and `--fake` swap them without code changes.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from anthropic import APIError, AsyncAnthropic

from app.research import events as ev
from app.research.brief import build_brief
from app.research.deep_pass import LogFn, run_deep_pass
from app.research.events import EventLog, LeakGuard
from app.research.fast_pass import run_fast_pass
from app.research.models import (
    R1,
    R2,
    CaseBrief,
    DeepFindings,
    FastPassOutput,
    LegitimacySignals,
    QuestionAnswer,
    ResearchDeepPayload,
    ResearchFastPayload,
    ResearchQuestionPayload,
    Verification,
)
from app.research.preprocess import ContentBlock, UnsupportedMedia, to_content_blocks
from app.research.question import answer_question, letter_context
from app.research.sim.settings import ResearchSettings
from app.research.sim.store import CaseRecord, Job, JobType, Store
from app.research.verify_cache import VerifyCache

# SIM: drop this fallback when Track A lands fast_pass.FastPassError
try:
    from app.research.fast_pass import FastPassError
except ImportError:

    class FastPassError(RuntimeError):  # type: ignore[no-redef]
        """The fast pass can't produce a trustworthy R1."""


logger = logging.getLogger(__name__)

# Failure rules (Plan.md): slow notice at 45 s, keep waiting to a hard cap.
FAST_SLOW_S = 45.0
FAST_CAP_S = 120.0
DEEP_TIMEOUT_S = 180.0
QUESTION_TIMEOUT_S = 30.0

ToBlocksFn = Callable[[bytes, str], Awaitable[list[ContentBlock]]]
FastPassFn = Callable[..., Awaitable[FastPassOutput]]
DeepPassFn = Callable[..., Awaitable[DeepFindings]]
QuestionFn = Callable[..., Awaitable[QuestionAnswer]]


@dataclass
class ResearchDeps:
    """Everything a handler calls out to. Defaults are the real passes."""

    settings: ResearchSettings
    anthropic: AsyncAnthropic | None = None
    http: httpx.AsyncClient | None = None
    fast_pass_fn: FastPassFn = run_fast_pass
    deep_pass_fn: DeepPassFn = run_deep_pass
    to_blocks_fn: ToBlocksFn = to_content_blocks
    question_fn: QuestionFn = answer_question
    seed: VerifyCache | None = None
    fast_slow_s: float = FAST_SLOW_S
    fast_cap_s: float = FAST_CAP_S
    deep_timeout_s: float = DEEP_TIMEOUT_S
    question_timeout_s: float = QUESTION_TIMEOUT_S


async def handle_research_fast(job: Job, store: Store, deps: ResearchDeps) -> None:
    """Run a `research_fast` job end to end (H1 -> R1).

    Reads the documents, runs the fast pass, writes `cases` and `case_refs`,
    queues `memory_write` and (on status ok) `research_deep`, logs
    `research.fast_*` events, and sets the job result to R1.
    """
    guard = LeakGuard()
    log = EventLog(store, guard, case_id=job.case_id, job_id=job.job_id)
    try:
        await _run_fast(job, store, deps, guard, log)
    except (FastPassError, TimeoutError) as exc:
        error = (
            f"fast pass exceeded {deps.fast_cap_s:.0f} s"
            if isinstance(exc, TimeoutError)
            else f"fast pass failed ({type(exc).__name__})"
        )
        await _fail(store, log, ev.FAST_FAILED, error)
    except Exception as exc:
        await _fail(store, log, ev.FAST_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_fast(
    job: Job, store: Store, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchFastPayload.model_validate(job.payload)
    case_id = payload.case_id
    await store.update_job(job.job_id, "running")
    await log.emit(ev.FAST_STARTED, "Started reading the letter")

    output = await _read_letter(payload, store, deps, log)
    guard.add(sv.value for sv in output.sensitive_values)
    r1 = output.r1

    for sv in output.sensitive_values:
        ref = await store.insert_case_ref(case_id, sv.field, sv.value)
        if ref != sv.ref:
            raise ValueError(f"store returned {ref} for {sv.ref}")

    if r1.status != "needs_better_image":
        case = CaseRecord(
            case_id=case_id,
            user_id=payload.user_id,
            document_ids=payload.document_ids,
            r1=r1,
            signals=output.signals,
            call_purpose=output.call_purpose,
        )
        guard.check("cases row", case.model_dump(mode="json"))
        await store.insert_case(case)

    if r1.proposed_facts:
        await _queue(
            store,
            guard,
            "memory_write",
            {
                "job": "memory_write",
                "user_id": payload.user_id,
                "source": "from_document",
                "source_ref": payload.document_ids[0],
                "proposed_facts": [
                    f.model_dump(mode="json") for f in r1.proposed_facts
                ],
            },
            case_id,
        )
    if r1.status == "ok":
        deep = ResearchDeepPayload(
            case_id=case_id,
            user_id=payload.user_id,
            document_ids=payload.document_ids,
        )
        await _queue(
            store, guard, "research_deep", deep.model_dump(mode="json"), case_id
        )

    await _finish(store, guard, job.job_id, r1.model_dump(mode="json"))
    await log.emit(
        ev.FAST_DONE,
        f"Finished reading the letter: {r1.status}",
        {"status": r1.status, "doc_type": r1.doc_type},
    )


async def _read_letter(
    payload: ResearchFastPayload, store: Store, deps: ResearchDeps, log: EventLog
) -> FastPassOutput:
    """Convert every page in order and run the fast pass with the slow/cap rule."""
    blocks: list[ContentBlock] = []
    try:
        for document_id in payload.document_ids:
            document = await store.get_document(document_id)
            for page in document.pages:
                blocks.extend(await deps.to_blocks_fn(page.data, page.content_type))
    except UnsupportedMedia as exc:
        r1 = R1(
            case_id=payload.case_id, status="needs_better_image", image_issue=str(exc)
        )
        return FastPassOutput(r1=r1, signals=LegitimacySignals())

    model = deps.settings.model_default
    task = asyncio.ensure_future(
        deps.fast_pass_fn(
            blocks, case_id=payload.case_id, client=deps.anthropic, model=model
        )
    )
    done, _ = await asyncio.wait({task}, timeout=deps.fast_slow_s)
    if not done:
        await log.emit(
            ev.FAST_SLOW,
            "Reading the letter is taking longer than usual",
            {"after_s": deps.fast_slow_s},
        )
        return await asyncio.wait_for(task, deps.fast_cap_s - deps.fast_slow_s)
    return task.result()


async def handle_research_deep(job: Job, store: Store, deps: ResearchDeps) -> None:
    """Run a `research_deep` job end to end (-> R2 + brief).

    Reads the case's signals, runs the deep pass, writes `verifications` and
    `case_briefs`, logs `research.deep_*` and `verification.*` events, and
    sets the job result to R2.
    """
    # Sensitive values stay in the fast job's memory; the deep pass never sees them.
    guard = LeakGuard()
    log = EventLog(store, guard, case_id=job.case_id, job_id=job.job_id)
    try:
        await _run_deep(job, store, deps, guard, log)
    except Exception as exc:
        await _fail(store, log, ev.DEEP_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_deep(
    job: Job, store: Store, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchDeepPayload.model_validate(job.payload)
    await store.update_job(job.job_id, "running")
    await log.emit(ev.DEEP_STARTED, "Started checking the letter is legitimate")
    case = await store.get_case(payload.case_id)
    county = payload.answers.get("county") or case.signals.county

    async def research_log(
        event_type: str, summary_en: str, data: dict[str, Any]
    ) -> None:
        if event_type not in ev.RESEARCH_LOG_TYPES:
            raise ValueError(f"deep pass logged unknown event type {event_type!r}")
        await log.emit(event_type, summary_en, data)

    try:
        findings = await asyncio.wait_for(
            _call_deep_pass(deps, case, county, research_log), deps.deep_timeout_s
        )
    except (TimeoutError, httpx.HTTPError, APIError) as exc:
        reason = (
            f"The check did not finish within {deps.deep_timeout_s:.0f} seconds"
            if isinstance(exc, TimeoutError)
            else "The check could not reach the web or the model"
        )
        logger.warning(
            "deep pass failed case_id=%s job_id=%s error=%s",
            payload.case_id,
            job.job_id,
            type(exc).__name__,
        )
        findings = DeepFindings(
            verification=Verification(status="unknown", evidence=[reason])
        )
        await log.emit(
            ev.DEEP_FAILED,
            "Could not finish checking the letter; result is unknown",
            {"error": type(exc).__name__},
        )

    verification = findings.verification
    if verification.status not in ev.VERIFICATION_EVENT:
        raise ValueError(f"deep pass returned status {verification.status!r}")
    guard.check("verifications row", verification.model_dump(mode="json"))
    ver_id = await store.insert_verification(payload.case_id, verification)

    brief: CaseBrief | None = None
    if verification.status == "verified":
        brief = build_brief(case, findings)
        guard.check("case_briefs row", brief.model_dump(mode="json"))
        await store.insert_case_brief(brief)

    r2 = R2(
        case_id=payload.case_id,
        verification=verification,
        official_phone_purpose=findings.official_phone_purpose,
        alternative_contacts=findings.alternative_contacts,
        call_recommended=(
            verification.status == "verified"
            and verification.official_phone is not None
        ),
        brief_id=brief.brief_id if brief else None,
        call_goal_en=brief.call_goal_en if brief else findings.call_goal_en,
    )
    await _finish(store, guard, job.job_id, r2.model_dump(mode="json"))
    await log.emit(
        ev.VERIFICATION_EVENT[verification.status],
        f"Letter verification: {verification.status}",
        {"ver_id": ver_id, "red_flag_count": len(verification.red_flags)},
    )
    await log.emit(
        ev.DEEP_DONE,
        "Finished checking the letter",
        {"ver_id": ver_id, "call_recommended": r2.call_recommended},
    )


async def handle_research_question(job: Job, store: Store, deps: ResearchDeps) -> None:
    """Run a `research_question` job: answer one process question from official pages.

    Never talks to the user; the orchestrator reads the job result (QuestionAnswer)
    and relays it. Logs `research.question_*` events without the question text.
    """
    guard = LeakGuard()
    log = EventLog(store, guard, case_id=job.case_id, job_id=job.job_id)
    try:
        await _run_question(job, store, deps, guard, log)
    except Exception as exc:
        await _fail(store, log, ev.QUESTION_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_question(
    job: Job, store: Store, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchQuestionPayload.model_validate(job.payload)
    await store.update_job(job.job_id, "running")
    await log.emit(ev.QUESTION_STARTED, "Started researching a question")
    sensitive: list[str] = []
    letter: str | None = None
    if payload.case_id:
        sensitive = list((await store.get_case_refs(payload.case_id)).values())
        letter = letter_context((await store.get_case(payload.case_id)).r1)
    guard.add(sensitive)

    async def research_log(
        event_type: str, summary_en: str, data: dict[str, Any]
    ) -> None:
        if event_type not in ev.RESEARCH_LOG_TYPES:
            raise ValueError(f"question pass logged unknown event type {event_type!r}")
        await log.emit(event_type, summary_en, data)

    try:
        answer = await asyncio.wait_for(
            deps.question_fn(
                payload.question_en,
                letter=letter,
                sensitive=sensitive,
                client=deps.anthropic,
                model=deps.settings.model_default,
                http=deps.http,
                log=research_log,
            ),
            deps.question_timeout_s,
        )
    except (TimeoutError, httpx.HTTPError, APIError) as exc:
        reason = (
            f"The research did not finish within {deps.question_timeout_s:.0f} seconds"
            if isinstance(exc, TimeoutError)
            else "The research could not reach the web or the model"
        )
        logger.warning(
            "question pass failed case_id=%s job_id=%s error=%s",
            payload.case_id,
            job.job_id,
            type(exc).__name__,
        )
        answer = QuestionAnswer(status="not_confirmed", reason_en=reason)
        await log.emit(
            ev.QUESTION_FAILED,
            "Could not finish researching the question; result is not_confirmed",
            {"error": type(exc).__name__},
        )

    await _finish(store, guard, job.job_id, answer.model_dump(mode="json"))
    await log.emit(
        ev.QUESTION_DONE,
        f"Finished researching a question: {answer.status}",
        {"status": answer.status, "source_count": len(answer.sources)},
    )


async def _call_deep_pass(
    deps: ResearchDeps, case: CaseRecord, county: str | None, log_fn: LogFn
) -> DeepFindings:
    kwargs: dict[str, Any] = {
        "client": deps.anthropic,
        "model": deps.settings.model_deep,
        "http": deps.http,
        "log": log_fn,
    }
    # Track B may add a doc_type kwarg; pass it only when the function takes it.
    params = inspect.signature(deps.deep_pass_fn).parameters
    any_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    if "doc_type" in params or any_kwargs:
        kwargs["doc_type"] = case.r1.doc_type
    if deps.seed is not None and ("seed" in params or any_kwargs):
        kwargs["seed"] = deps.seed
    return await deps.deep_pass_fn(case.signals, case.call_purpose, county, **kwargs)


async def _queue(
    store: Store,
    guard: LeakGuard,
    job_type: JobType,
    payload: dict[str, Any],
    case_id: str,
) -> None:
    guard.check(f"{job_type} payload", payload)
    await store.create_job(job_type, payload, case_id=case_id)


async def _finish(
    store: Store, guard: LeakGuard, job_id: str, result: dict[str, Any]
) -> None:
    guard.check("job result", result)
    await store.update_job(job_id, "done", result=result)


async def _fail(store: Store, log: EventLog, event_type: str, error: str) -> None:
    """Mark the job failed and log it. `error` is our own text, never exception content."""
    logger.warning(
        "%s case_id=%s job_id=%s error=%s", event_type, log.case_id, log.job_id, error
    )
    await store.update_job(log.job_id, "failed", error=error)
    await log.emit(event_type, f"Job failed: {error}", {"error": error})
