import asyncio
import dataclasses
import json
from typing import Any

import httpx
import pytest

from research import events as ev
from research.events import EventLog, LeakDetected, LeakGuard
from research.fake import fake_deep_findings, fake_fast_pass_output
from research.jobs import (
    FastPassError,
    ResearchDeps,
    handle_research_deep,
    handle_research_fast,
)
from research.models import (
    R1,
    R2,
    REQUIRED_MUST_NOT_DO,
    DeepFindings,
    FastPassOutput,
    ResearchDeepPayload,
    ResearchFastPayload,
    Verification,
)
from research.sim.memory import InMemoryStore
from research.sim.run import fake_deps
from research.sim.store import CaseRecord, Document, DocumentPage, Job

pytestmark = pytest.mark.asyncio

SECRET = fake_fast_pass_output().sensitive_values[0].value


def deps(**overrides: Any) -> ResearchDeps:
    return dataclasses.replace(fake_deps(), **overrides)


def types(store: InMemoryStore) -> list[str]:
    return [e.type for e in store.events]


def job_types(store: InMemoryStore) -> list[str]:
    return [j.type for j in store.jobs.values()]


async def fast_job(
    store: InMemoryStore, pages: list[DocumentPage] | None = None
) -> Job:
    pages = pages or [DocumentPage(content_type="image/jpeg", data=b"p1")]
    await store.insert_document(
        Document(document_id="doc_1", user_id="user_1", pages=pages)
    )
    payload = ResearchFastPayload(
        case_id="case_1", user_id="user_1", document_ids=["doc_1"], user_language="es"
    )
    job_id = await store.create_job(
        "research_fast", payload.model_dump(mode="json"), "case_1"
    )
    return store.jobs[job_id]


async def deep_job(store: InMemoryStore, answers: dict[str, str] | None = None) -> Job:
    out = fake_fast_pass_output("case_1")
    await store.insert_case(
        CaseRecord(
            case_id="case_1",
            user_id="user_1",
            document_ids=["doc_1"],
            r1=out.r1,
            signals=out.signals.model_copy(update={"county": "Signal County"}),
            call_purpose=out.call_purpose,
        )
    )
    payload = ResearchDeepPayload(
        case_id="case_1",
        user_id="user_1",
        document_ids=["doc_1"],
        answers=answers or {},
    )
    job_id = await store.create_job(
        "research_deep", payload.model_dump(mode="json"), "case_1"
    )
    return store.jobs[job_id]


# --- research_fast ---


async def test_fast_happy_path() -> None:
    store = InMemoryStore()
    seen: list[Any] = []

    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        seen.extend(blocks)
        return fake_fast_pass_output(case_id)

    pages = [
        DocumentPage(content_type="image/jpeg", data=f"page{i}".encode())
        for i in range(3)
    ]
    job = await fast_job(store, pages)
    await handle_research_fast(job, store, deps(fast_pass_fn=fast))

    done = store.jobs[job.job_id]
    assert done.status == "done"
    r1 = R1.model_validate(done.result)
    assert r1.status == "ok"
    assert [b["source"]["data"] for b in seen] == ["cGFnZTA=", "cGFnZTE=", "cGFnZTI="]
    assert store.case_refs == {("case_1", "case_number"): SECRET}
    assert store.cases["case_1"].call_purpose == "Confirm the form was received"
    assert job_types(store) == ["research_fast", "memory_write", "research_deep"]
    memory = next(j for j in store.jobs.values() if j.type == "memory_write")
    assert memory.payload["source"] == "from_document"
    assert memory.payload["source_ref"] == "doc_1"
    assert types(store) == [ev.FAST_STARTED, ev.FAST_DONE]
    assert store.events[-1].data == {
        "status": "ok",
        "doc_type": "generic_agency_notice",
    }
    assert all(e.source == "research_agent" for e in store.events)


async def test_fast_needs_better_image_queues_no_deep() -> None:
    store = InMemoryStore()

    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        out = fake_fast_pass_output(case_id)
        r1 = R1(case_id=case_id, status="needs_better_image", image_issue="Too blurry")
        return out.model_copy(update={"r1": r1, "sensitive_values": []})

    job = await fast_job(store)
    await handle_research_fast(job, store, deps(fast_pass_fn=fast))

    assert store.jobs[job.job_id].result["status"] == "needs_better_image"
    assert "research_deep" not in job_types(store)
    assert store.cases == {}


async def test_unsupported_media_becomes_needs_better_image() -> None:
    store = InMemoryStore()

    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise AssertionError("fast pass must not run")

    job = await fast_job(store, [DocumentPage(content_type="image/heic", data=b"x")])
    await handle_research_fast(job, store, deps(fast_pass_fn=fast))

    r1 = R1.model_validate(store.jobs[job.job_id].result)
    assert r1.status == "needs_better_image"
    assert r1.image_issue and "JPG" in r1.image_issue
    assert job_types(store) == ["research_fast"]


async def test_slow_fast_pass_emits_fast_slow_then_succeeds() -> None:
    store = InMemoryStore()

    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        await asyncio.sleep(0.05)
        return fake_fast_pass_output(case_id)

    job = await fast_job(store)
    await handle_research_fast(
        job, store, deps(fast_pass_fn=fast, fast_slow_s=0.01, fast_cap_s=1.0)
    )

    assert store.jobs[job.job_id].status == "done"
    assert types(store) == [ev.FAST_STARTED, ev.FAST_SLOW, ev.FAST_DONE]


async def test_fast_pass_over_hard_cap_fails_job() -> None:
    store = InMemoryStore()

    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        await asyncio.sleep(1)
        raise AssertionError("should have been cancelled")

    job = await fast_job(store)
    await handle_research_fast(
        job, store, deps(fast_pass_fn=fast, fast_slow_s=0.01, fast_cap_s=0.05)
    )

    failed = store.jobs[job.job_id]
    assert failed.status == "failed"
    assert "exceeded" in (failed.error or "")
    assert types(store) == [ev.FAST_STARTED, ev.FAST_SLOW, ev.FAST_FAILED]
    assert store.cases == {}


async def test_fast_pass_error_fails_job_with_event() -> None:
    store = InMemoryStore()

    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise FastPassError("model refused")

    job = await fast_job(store)
    await handle_research_fast(job, store, deps(fast_pass_fn=fast))

    assert store.jobs[job.job_id].status == "failed"
    assert types(store) == [ev.FAST_STARTED, ev.FAST_FAILED]
    assert job_types(store) == ["research_fast"]


async def test_unexpected_error_fails_job_then_propagates() -> None:
    store = InMemoryStore()

    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise KeyError("bug")

    job = await fast_job(store)
    with pytest.raises(KeyError):
        await handle_research_fast(job, store, deps(fast_pass_fn=fast))
    assert store.jobs[job.job_id].status == "failed"
    assert types(store)[-1] == ev.FAST_FAILED


# --- research_deep ---


async def test_deep_happy_path() -> None:
    store = InMemoryStore()
    job = await deep_job(store)
    await handle_research_deep(job, store, deps())

    r2 = R2.model_validate(store.jobs[job.job_id].result)
    assert r2.call_recommended is True
    assert r2.verification.status == "verified"
    [(ver_id, (case_id, verification))] = store.verifications.items()
    assert case_id == "case_1" and verification.official_phone
    brief = store.case_briefs[r2.brief_id]
    assert all(rule in brief.must_not_do for rule in REQUIRED_MUST_NOT_DO)
    assert types(store) == [
        ev.DEEP_STARTED,
        ev.SEARCH,
        ev.FETCH,
        ev.CHECK,
        ev.VERIFIED,
        ev.DEEP_DONE,
    ]
    assert store.events[4].data == {"ver_id": ver_id, "red_flag_count": 0}


async def test_deep_suspicious_has_no_brief_and_no_call() -> None:
    store = InMemoryStore()

    async def deep(*_: Any, **__: Any) -> DeepFindings:
        return DeepFindings(
            verification=Verification(
                status="suspicious", red_flags=["Demands payment by gift card"]
            )
        )

    job = await deep_job(store)
    await handle_research_deep(job, store, deps(deep_pass_fn=deep))

    r2 = R2.model_validate(store.jobs[job.job_id].result)
    assert r2.call_recommended is False and r2.brief_id is None
    assert store.case_briefs == {}
    verdict = next(e for e in store.events if e.type == ev.SUSPICIOUS)
    assert verdict.data["red_flag_count"] == 1


@pytest.mark.parametrize("failure", ["timeout", "network"])
async def test_deep_failure_finishes_with_unknown(failure: str) -> None:
    store = InMemoryStore()

    async def deep(*_: Any, **__: Any) -> DeepFindings:
        if failure == "network":
            raise httpx.ConnectError("down")
        await asyncio.sleep(1)
        raise AssertionError("should have been cancelled")

    job = await deep_job(store)
    await handle_research_deep(job, store, deps(deep_pass_fn=deep, deep_timeout_s=0.02))

    done = store.jobs[job.job_id]
    assert done.status == "done"
    r2 = R2.model_validate(done.result)
    assert r2.verification.status == "unknown"
    assert r2.verification.evidence and r2.call_recommended is False
    assert types(store) == [ev.DEEP_STARTED, ev.DEEP_FAILED, ev.UNKNOWN, ev.DEEP_DONE]


async def test_deep_programming_error_fails_loudly() -> None:
    store = InMemoryStore()

    async def deep(*_: Any, **__: Any) -> DeepFindings:
        raise TypeError("bug")

    job = await deep_job(store)
    with pytest.raises(TypeError):
        await handle_research_deep(job, store, deps(deep_pass_fn=deep))
    assert store.jobs[job.job_id].status == "failed"
    assert types(store)[-1] == ev.DEEP_FAILED


@pytest.mark.parametrize(
    ("answers", "expected"),
    [({"county": "Alameda"}, "Alameda"), ({}, "Signal County")],
)
async def test_county_from_answers_then_signals(
    answers: dict[str, str], expected: str
) -> None:
    store = InMemoryStore()
    seen: dict[str, Any] = {}

    async def deep(
        signals: Any, call_purpose: Any, county: Any, **_: Any
    ) -> DeepFindings:
        seen["county"] = county
        return fake_deep_findings()

    job = await deep_job(store, answers)
    await handle_research_deep(job, store, deps(deep_pass_fn=deep))
    assert seen["county"] == expected


async def test_doc_type_passed_only_when_accepted() -> None:
    seen: dict[str, Any] = {}

    async def with_doc_type(
        signals: Any, call_purpose: Any, county: Any, *, doc_type: str | None, **_: Any
    ) -> DeepFindings:
        seen["doc_type"] = doc_type
        return fake_deep_findings()

    async def without_doc_type(
        signals: Any,
        call_purpose: Any,
        county: Any,
        *,
        client: Any,
        model: str,
        http: Any,
        log: Any,
    ) -> DeepFindings:
        return fake_deep_findings()

    store = InMemoryStore()
    await handle_research_deep(
        await deep_job(store), store, deps(deep_pass_fn=with_doc_type)
    )
    assert seen["doc_type"] == "generic_agency_notice"

    store = InMemoryStore()
    job = await deep_job(store)
    await handle_research_deep(job, store, deps(deep_pass_fn=without_doc_type))
    assert store.jobs[job.job_id].status == "done"


async def test_log_fn_events_land_in_store() -> None:
    store = InMemoryStore()

    async def deep(*_: Any, log: Any, **__: Any) -> DeepFindings:
        await log(ev.FETCH, "Fetched a page", {"url": "https://www.example.gov/"})
        return fake_deep_findings()

    job = await deep_job(store)
    await handle_research_deep(job, store, deps(deep_pass_fn=deep))

    fetch = next(e for e in store.events if e.type == ev.FETCH)
    assert fetch.data == {"url": "https://www.example.gov/"}
    assert fetch.job_id == job.job_id and fetch.case_id == "case_1"


# --- Leak guard ---


async def test_leak_in_job_result_raises_and_fails_job() -> None:
    store = InMemoryStore()

    async def leaky(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        out = fake_fast_pass_output(case_id)
        r1 = out.r1.model_copy(update={"explanation_en": f"Your case is {SECRET}."})
        return out.model_copy(update={"r1": r1})

    job = await fast_job(store)
    with pytest.raises(LeakDetected):
        await handle_research_fast(job, store, deps(fast_pass_fn=leaky))

    assert store.jobs[job.job_id].status == "failed"
    assert types(store)[-1] == ev.FAST_FAILED
    written = json.dumps(
        [e.model_dump(mode="json") for e in store.events]
        + [j.model_dump(mode="json") for j in store.jobs.values()]
        + [c.model_dump(mode="json") for c in store.cases.values()]
    )
    assert SECRET not in written


async def test_leak_in_event_raises_before_write() -> None:
    store = InMemoryStore()
    guard = LeakGuard()
    guard.add([SECRET])
    log = EventLog(store, guard, case_id="case_1", job_id="job_1")

    with pytest.raises(LeakDetected) as exc:
        await log.emit(ev.CHECK, "checked", {"note": f"saw {SECRET}"})
    assert SECRET not in str(exc.value)
    assert store.events == []
