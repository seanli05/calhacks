"""The `memory_write` job (Plan.md → Jobs; Goal 7.1–7.4).

A `user_said` job carries only the message ID: the writer reads the message and
extracts facts with the fast model. Research and the phone agent send their facts
in `proposed_facts`. Either way every fact goes through `filters.py` (C25, C34),
is checked against what's already stored, and is saved with its `source` and
`source_ref`. Every job ends finished or failed.

Logs and events carry IDs and counts, never fact text (C27): a dropped fact may be
an asylum detail.
"""

import asyncio
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.contracts import (
    EventType,
    FactSource,
    FactStatus,
    MemoryWriteJob,
    MessageDirection,
    Sensitivity,
)
from app.contracts.common import FactId
from app.db import jobs, reads, tables
from app.db.writes import memory as writes
from app.memory.events import fact_event
from app.memory.extract import ExtractedProfile, ExtractionError, FactExtractor
from app.memory.filters import Candidate, new_facts, storable

logger = logging.getLogger(__name__)

JOB_TIMEOUT_S = 60.0
_KNOWN = (FactStatus.ACTIVE, FactStatus.PENDING_CONSENT)


@dataclass
class MemoryDeps:
    extractor: FactExtractor | None
    """None without an Anthropic key: `user_said` jobs then fail, others still run."""
    job_timeout_s: float = JOB_TIMEOUT_S


class MemoryWriteOutcome(BaseModel):
    """The job's result: what was stored, by ID, and how much was left out."""

    saved: list[FactId] = Field(default_factory=list)
    pending_consent: list[FactId] = Field(default_factory=list)
    dropped: int = 0
    duplicates: int = 0
    profile_keys: list[str] = Field(default_factory=list)
    skipped: str | None = None


async def handle_memory_write(job: tables.Job, deps: MemoryDeps) -> None:
    try:
        payload = MemoryWriteJob.model_validate(job.payload)
        async with asyncio.timeout(deps.job_timeout_s):
            outcome = await _write(job, payload, deps)
    except ValidationError:
        await _fail(job, "payload is not a MemoryWriteJob")
        return
    except ExtractionError as exc:
        await _fail(job, str(exc))
        return
    except TimeoutError:
        await _fail(job, f"memory write exceeded {deps.job_timeout_s:.0f} s")
        return
    except Exception as exc:
        await _fail(job, f"unexpected {type(exc).__name__}")
        raise
    await jobs.finish(job.id, outcome)
    logger.info(
        "Memory write done user_id=%s job_id=%s saved=%d pending=%d dropped=%d "
        "duplicates=%d skipped=%s",
        job.user_id,
        job.id,
        len(outcome.saved),
        len(outcome.pending_consent),
        outcome.dropped,
        outcome.duplicates,
        outcome.skipped,
    )


async def _write(
    job: tables.Job, payload: MemoryWriteJob, deps: MemoryDeps
) -> MemoryWriteOutcome:
    known = await reads.list_facts(payload.user_id, _KNOWN)
    profile = ExtractedProfile()
    if payload.proposed_facts:
        # Proposed facts carry no category. Research marks immigration facts
        # sensitive (ProposedFact); the filter catches immigration facts it didn't.
        candidates = [
            Candidate(
                f.fact,
                "immigration" if f.sensitivity == Sensitivity.SENSITIVE else "other",
                f.source,
                f.sensitivity == Sensitivity.SENSITIVE,
            )
            for f in payload.proposed_facts
        ]
    elif payload.source == FactSource.USER_SAID:
        message, previous = await _message_and_reply(payload)
        skipped = _skip_reason(message)
        if skipped is not None:
            return MemoryWriteOutcome(skipped=skipped)
        assert message is not None and message.body_en is not None
        if deps.extractor is None:
            raise ExtractionError("no extractor (ANTHROPIC_API_KEY not set)")
        extraction = await deps.extractor.extract(
            message.body_en,
            previous.body_en if previous else None,
            [fact.fact for fact in known],
        )
        candidates = [
            Candidate(f.fact, f.category, FactSource.USER_SAID)
            for f in extraction.facts
        ]
        profile = extraction.profile
    else:
        return MemoryWriteOutcome(skipped="no facts proposed")

    outcome = MemoryWriteOutcome()
    allowed = [s for s in map(storable, candidates) if s is not None]
    outcome.dropped = len(candidates) - len(allowed)
    fresh = new_facts(allowed, [fact.fact for fact in known])
    outcome.duplicates = len(allowed) - len(fresh)
    for fact in fresh:
        row = await writes.add_fact(
            payload.user_id,
            fact.fact,
            fact.category,
            fact.source,
            fact.sensitivity,
            fact.status,
            source_ref=payload.source_ref,
        )
        if fact.status == FactStatus.PENDING_CONSENT:
            outcome.pending_consent.append(row.id)
            event_type = EventType.MEMORY_FACT_PENDING_CONSENT
            summary = "Holding a sensitive fact until the user says it's OK"
        else:
            outcome.saved.append(row.id)
            event_type = EventType.MEMORY_FACT_SAVED
            summary = "Saved a fact"
        await fact_event(
            event_type,
            payload.user_id,
            row.id,
            summary,
            case_id=job.case_id,
            job_id=job.id,
        )
    outcome.profile_keys = await _save_profile(payload, profile)
    return outcome


async def _message_and_reply(
    payload: MemoryWriteJob,
) -> tuple[tables.Message | None, tables.Message | None]:
    """The user's message (`source_ref`) and the reply sent just before it, which
    gives short answers their meaning."""
    messages = await reads.list_messages(payload.user_id)
    for i, message in enumerate(messages):
        if message.id == payload.source_ref:
            previous = next(
                (
                    m
                    for m in reversed(messages[:i])
                    if m.direction == MessageDirection.OUT
                ),
                None,
            )
            return message, previous
    return None, None


def _skip_reason(message: tables.Message | None) -> str | None:
    """Why there's nothing to read in this message, or None."""
    if message is None:
        return "message not found"  # deleted by the user since (C26)
    if message.direction != MessageDirection.IN:
        return "not a user message"
    if message.body_en is None:
        return "no English text"  # translation failed at the edge (rule 6)
    if not any(ch.isalpha() for ch in message.body_en):
        return "no words"  # "1", "2", an emoji
    return None


async def _save_profile(
    payload: MemoryWriteJob, profile: ExtractedProfile
) -> list[str]:
    """Short keys, plain values: the dashboard shows each as label and value."""
    fields: dict[str, str] = {}
    if profile.county and profile.county.strip():
        county = profile.county.strip()
        fields["county"] = county.removesuffix(" County").removesuffix(" county")
    if profile.household_size is not None and 1 <= profile.household_size <= 30:
        fields["household_size"] = str(profile.household_size)
    if profile.contact_preference and profile.contact_preference.strip():
        fields["contact_preference"] = profile.contact_preference.strip()
    if any(
        storable(Candidate(value, "contact", payload.source)) is None
        for value in fields.values()
    ):
        # A value with an identifier or a claim detail in it: store none of them.
        logger.warning("Profile fields dropped user_id=%s", payload.user_id)
        return []
    if fields:
        await writes.upsert_profile(payload.user_id, fields)
    return sorted(fields)


async def _fail(job: tables.Job, error: str) -> None:
    logger.error(
        "Memory write failed user_id=%s job_id=%s: %s", job.user_id, job.id, error
    )
    await jobs.fail(job.id, error)
