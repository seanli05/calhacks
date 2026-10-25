"""Job handlers: the only research code that touches the database.

Each handler takes a claimed `jobs` row (already `running`), reads what it needs,
runs one pass, writes the tables research owns (`cases`, `case_refs`,
`verifications`, `case_briefs`) through `app.db.writes.research`, queues
follow-up jobs, and logs events. Passes come in through `ResearchDeps` so tests
and `--fake` swap them without code changes.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from anthropic import APIError, AsyncAnthropic
from pydantic import BaseModel

from app.contracts import (
    Component,
    DeepResult,
    FactSource,
    FastResult,
    JobPayload,
    LegitimacySignals,
    MemoryWriteJob,
    QuestionAnswer,
    ResearchDeepJob,
    ResearchFastJob,
    ResearchQuestionJob,
    Verification,
    VerificationStatus,
)
from app.db import jobs as db_jobs
from app.db import reads, tables
from app.db.writes import research as writes
from app.research import events as ev
from app.research.brief import build_brief
from app.research.deep_pass import LogFn, run_deep_pass
from app.research.events import EventLog, LeakGuard
from app.research.fast_pass import FastPassError, run_fast_pass
from app.research.fetch_tool import registered_domain
from app.research.instant_check import instant_red_flags
from app.research.models import CaseRecord, DeepFindings, FastPassOutput
from app.research.preprocess import ContentBlock, UnsupportedMedia, to_content_blocks
from app.research.question import answer_question, letter_context
from app.research.short_goal import shorten_goal
from app.research.verify_cache import VerifyCache
from app.settings import Settings

logger = logging.getLogger(__name__)

# Failure rules (Plan.md): slow notice at 45 s, keep waiting to a hard cap.
FAST_SLOW_S = 45.0
FAST_CAP_S = 120.0
DEEP_TIMEOUT_S = 180.0
QUESTION_TIMEOUT_S = 30.0
SHORT_GOAL_TIMEOUT_S = 10.0

ToBlocksFn = Callable[[bytes, str], Awaitable[list[ContentBlock]]]
FastPassFn = Callable[..., Awaitable[FastPassOutput]]
DeepPassFn = Callable[..., Awaitable[DeepFindings]]
QuestionFn = Callable[..., Awaitable[QuestionAnswer]]
ShortGoalFn = Callable[..., Awaitable[str | None]]


@dataclass
class ResearchDeps:
    """Everything a handler calls out to. Defaults are the real passes."""

    settings: Settings
    anthropic: AsyncAnthropic | None = None
    http: httpx.AsyncClient | None = None
    fast_pass_fn: FastPassFn = run_fast_pass
    deep_pass_fn: DeepPassFn = run_deep_pass
    to_blocks_fn: ToBlocksFn = to_content_blocks
    question_fn: QuestionFn = answer_question
    short_goal_fn: ShortGoalFn = shorten_goal
    seed: VerifyCache | None = None
    fast_slow_s: float = FAST_SLOW_S
    fast_cap_s: float = FAST_CAP_S
    deep_timeout_s: float = DEEP_TIMEOUT_S
    question_timeout_s: float = QUESTION_TIMEOUT_S
    short_goal_timeout_s: float = SHORT_GOAL_TIMEOUT_S


async def handle_research_fast(job: tables.Job, deps: ResearchDeps) -> None:
    """Run a `research_fast` job end to end (H1 -> R1).

    Reads the documents, runs the fast pass and the instant checks (C45: scam
    signs mark R1 `suspicious`), writes `cases` and `case_refs`, queues
    `memory_write` and (on status ok) `research_deep`, logs `research.fast_*`
    events, and sets the job result to R1.
    """
    guard = LeakGuard()
    log = EventLog(guard, user_id=job.user_id, case_id=job.case_id, job_id=job.id)
    try:
        await _run_fast(job, deps, guard, log)
    except (FastPassError, TimeoutError) as exc:
        error = (
            f"fast pass exceeded {deps.fast_cap_s:.0f} s"
            if isinstance(exc, TimeoutError)
            else f"fast pass failed ({type(exc).__name__})"
        )
        await _fail(log, ev.FAST_FAILED, error)
    except Exception as exc:
        await _fail(log, ev.FAST_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_fast(
    job: tables.Job, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchFastJob.model_validate(job.payload)
    case_id = payload.case_id
    await log.emit(ev.FAST_STARTED, "Started reading the letter")

    output = await _read_letter(payload, deps, log)
    guard.add(sv.value for sv in output.sensitive_values)
    r1 = output.r1
    if r1.status == "ok":
        # C45: a letter with scam signs is flagged now, so it's never explained.
        red_flags = instant_red_flags(output.signals, r1.doc_type)
        await log.emit(
            ev.CHECK,
            f"Instant checks: {len(red_flags)} red flag(s)",
            {"check": "instant", "red_flags": red_flags},
        )
        if red_flags:
            r1 = r1.model_copy(update={"verification": VerificationStatus.SUSPICIOUS})

    # The case row comes first: refs and R1 hang off it. A re-read of the same
    # case (a better photo, or a needs_user_input reply) reuses the row.
    if await reads.get_case(case_id) is None:
        await writes.create_case(case_id, payload.user_id, payload.document_ids)
        await log.emit(ev.CASE_CREATED, "Opened a case for the letter")
    for sv in output.sensitive_values:
        if sv.ref != f"<ref:{sv.field}>":
            raise ValueError(f"ref {sv.ref} does not match field {sv.field}")
        await writes.put_ref(case_id, sv.field, sv.value)
    guard.check("cases row", r1.model_dump(mode="json"))
    await writes.save_fast_result(case_id, r1)

    if r1.proposed_facts:
        await _queue(
            guard,
            MemoryWriteJob(
                user_id=payload.user_id,
                source=FactSource.FROM_DOCUMENT,
                source_ref=payload.document_ids[0],
                proposed_facts=r1.proposed_facts,
            ),
            payload.user_id,
            case_id,
        )
    if r1.status == "ok":
        await _queue(
            guard,
            ResearchDeepJob(
                case_id=case_id,
                user_id=payload.user_id,
                document_ids=payload.document_ids,
                signals=output.signals,
                call_purpose=output.call_purpose,
            ),
            payload.user_id,
            case_id,
        )

    await _finish(guard, job.id, r1)
    await log.emit(
        ev.FAST_DONE,
        f"Finished reading the letter: {r1.status}",
        {"status": r1.status, "doc_type": r1.doc_type},
    )


async def _read_letter(
    payload: ResearchFastJob, deps: ResearchDeps, log: EventLog
) -> FastPassOutput:
    """Convert every page in order and run the fast pass with the slow/cap rule."""
    blocks: list[ContentBlock] = []
    try:
        for document_id in payload.document_ids:
            document = await reads.get_document(document_id)
            if document is None:
                raise ValueError(f"document {document_id} not found")
            for page in document.pages:
                media = await reads.get_media(page["media_id"])
                if media is None:
                    raise ValueError(f"media {page['media_id']} not found")
                blocks.extend(await deps.to_blocks_fn(media.data, media.content_type))
    except UnsupportedMedia as exc:
        r1 = FastResult(
            case_id=payload.case_id, status="needs_better_image", image_issue=str(exc)
        )
        return FastPassOutput(r1=r1, signals=LegitimacySignals())

    model = deps.settings.model_default
    task = asyncio.ensure_future(
        deps.fast_pass_fn(
            blocks,
            case_id=payload.case_id,
            client=deps.anthropic,
            model=model,
            # Only when set, so fast-pass fakes needn't accept it (C39).
            **({"user_note_en": payload.user_note_en} if payload.user_note_en else {}),
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


async def handle_research_deep(job: tables.Job, deps: ResearchDeps) -> None:
    """Run a `research_deep` job end to end (-> R2 + brief).

    Takes the signals from its payload, runs the deep pass, writes
    `verifications` and `case_briefs`, logs `research.deep_*` and
    `verification.*` events, and sets the job result to R2.
    """
    # Sensitive values stay in the fast job's memory; the deep pass never sees them.
    guard = LeakGuard()
    log = EventLog(guard, user_id=job.user_id, case_id=job.case_id, job_id=job.id)
    try:
        await _run_deep(job, deps, guard, log)
    except Exception as exc:
        await _fail(log, ev.DEEP_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_deep(
    job: tables.Job, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchDeepJob.model_validate(job.payload)
    await log.emit(ev.DEEP_STARTED, "Started checking the letter is legitimate")
    row = await reads.get_case(payload.case_id)
    if row is None or row.fast_result is None:
        raise ValueError(f"case {payload.case_id} has no fast result")
    case = CaseRecord(
        case_id=payload.case_id,
        user_id=payload.user_id,
        document_ids=payload.document_ids,
        r1=FastResult.model_validate(row.fast_result),
        signals=payload.signals,
        call_purpose=payload.call_purpose,
    )

    async def research_log(
        event_type: str, summary_en: str, data: dict[str, Any]
    ) -> None:
        if event_type not in ev.RESEARCH_LOG_TYPES:
            raise ValueError(f"deep pass logged unknown event type {event_type!r}")
        await log.emit(event_type, summary_en, data)

    try:
        findings = await asyncio.wait_for(
            _call_deep_pass(deps, case, case.signals.county, research_log),
            deps.deep_timeout_s,
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
            job.id,
            type(exc).__name__,
        )
        findings = DeepFindings(
            verification=Verification(
                status="unknown",
                official_phone=None,
                letter_phone_matches=None,
                evidence=[reason],
                red_flags=[],
            )
        )
        await log.emit(
            ev.DEEP_FAILED,
            "Could not finish checking the letter; result is unknown",
            {"error": type(exc).__name__},
        )

    verification = findings.verification
    if verification.status not in ev.VERIFICATION_EVENT:
        raise ValueError(f"deep pass returned status {verification.status!r}")
    # The dashboard shows the first evidence entry as the official source.
    source_url = findings.trust_chain[-1] if findings.trust_chain else None
    if verification.status == "verified" and source_url:
        evidence = [source_url, *(e for e in verification.evidence if e != source_url)]
        verification = verification.model_copy(update={"evidence": evidence})
    guard.check("verifications row", verification.model_dump(mode="json"))
    ver_row = await writes.save_verification(payload.case_id, verification)

    brief_id: str | None = None
    call_goal_en = findings.call_goal_en
    if verification.status == "verified":
        brief = build_brief(case, findings)
        guard.check("case_briefs row", brief.model_dump(mode="json"))
        await writes.save_brief(payload.case_id, brief)
        brief_id = brief.brief_id
        # The short goal the user reads (C41); the brief keeps the full one.
        call_goal_en = await _short_goal(deps, brief.call_goal_en, job.id)

    r2 = DeepResult(
        case_id=payload.case_id,
        verification=verification,
        official_phone_purpose=findings.official_phone_purpose,
        alternative_contacts=findings.alternative_contacts,
        call_recommended=(
            verification.status == "verified"
            and verification.official_phone is not None
        ),
        brief_id=brief_id,
        call_goal_en=call_goal_en,
    )
    await _finish(guard, job.id, r2)
    data: dict[str, Any] = {
        "ver_id": ver_row.id,
        "red_flag_count": len(verification.red_flags),
    }
    if verification.status == "verified" and source_url:
        data["source"] = registered_domain(source_url)
    await log.emit(
        ev.VERIFICATION_EVENT[verification.status],
        f"Letter verification: {verification.status}",
        data,
    )
    await log.emit(
        ev.DEEP_DONE,
        "Finished checking the letter",
        {"ver_id": ver_row.id, "call_recommended": r2.call_recommended},
    )


async def handle_research_question(job: tables.Job, deps: ResearchDeps) -> None:
    """Run a `research_question` job: answer one process question from official pages.

    Never talks to the user; the orchestrator reads the job result (QuestionAnswer)
    and relays it. Logs `research.question_*` events without the question text.
    """
    guard = LeakGuard()
    log = EventLog(guard, user_id=job.user_id, case_id=job.case_id, job_id=job.id)
    try:
        await _run_question(job, deps, guard, log)
    except Exception as exc:
        await _fail(log, ev.QUESTION_FAILED, f"unexpected {type(exc).__name__}")
        raise


async def _run_question(
    job: tables.Job, deps: ResearchDeps, guard: LeakGuard, log: EventLog
) -> None:
    payload = ResearchQuestionJob.model_validate(job.payload)
    await log.emit(ev.QUESTION_STARTED, "Started researching a question")
    sensitive: list[str] = []
    letter: str | None = None
    if payload.case_id:
        sensitive = [ref.value for ref in await reads.list_case_refs(payload.case_id)]
        case = await reads.get_case(payload.case_id)
        if case is not None and case.fast_result is not None:
            letter = letter_context(FastResult.model_validate(case.fast_result))
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
            job.id,
            type(exc).__name__,
        )
        answer = QuestionAnswer(status="not_confirmed", reason_en=reason)
        await log.emit(
            ev.QUESTION_FAILED,
            "Could not finish researching the question; result is not_confirmed",
            {"error": type(exc).__name__},
        )

    await _finish(guard, job.id, answer)
    await log.emit(
        ev.QUESTION_DONE,
        f"Finished researching a question: {answer.status}",
        {"status": answer.status, "source_count": len(answer.sources)},
    )


async def _short_goal(deps: ResearchDeps, goal_en: str, job_id: str) -> str | None:
    """None on any model or network failure: the consent question then uses the
    brief's goal, so a failure here never holds up R2."""
    try:
        return await asyncio.wait_for(
            deps.short_goal_fn(
                goal_en, client=deps.anthropic, model=deps.settings.model_fast
            ),
            deps.short_goal_timeout_s,
        )
    except (TimeoutError, httpx.HTTPError, APIError) as exc:
        logger.warning(
            "short goal failed job_id=%s error=%s", job_id, type(exc).__name__
        )
        return None


async def _call_deep_pass(
    deps: ResearchDeps, case: CaseRecord, county: str | None, log_fn: LogFn
) -> DeepFindings:
    kwargs: dict[str, Any] = {
        "client": deps.anthropic,
        "model": deps.settings.model_deep,
        "http": deps.http,
        "log": log_fn,
    }
    # Fakes may not take doc_type or seed; pass them only when the function does.
    params = inspect.signature(deps.deep_pass_fn).parameters
    any_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    if "doc_type" in params or any_kwargs:
        kwargs["doc_type"] = case.r1.doc_type
    if deps.seed is not None and ("seed" in params or any_kwargs):
        kwargs["seed"] = deps.seed
    return await deps.deep_pass_fn(case.signals, case.call_purpose, county, **kwargs)


async def _queue(
    guard: LeakGuard, payload: JobPayload, user_id: str, case_id: str
) -> None:
    guard.check(f"{payload.job} payload", payload.model_dump(mode="json"))
    await db_jobs.enqueue(payload, Component.RESEARCH_AGENT, user_id, case_id)


async def _finish(guard: LeakGuard, job_id: str, result: BaseModel) -> None:
    guard.check("job result", result.model_dump(mode="json"))
    await db_jobs.finish(job_id, result)


async def _fail(log: EventLog, event_type: str, error: str) -> None:
    """Mark the job failed and log it. `error` is our own text, never exception content."""
    logger.warning(
        "%s case_id=%s job_id=%s error=%s", event_type, log.case_id, log.job_id, error
    )
    await db_jobs.fail(log.job_id, error)
    await log.emit(event_type, f"Job failed: {error}", {"error": error})
