import asyncio
import dataclasses
import json
from typing import Any

import httpx
import pytest
from app.contracts import (
    REQUIRED_MUST_NOT_DO,
    DeepResult,
    FastResult,
    ResearchDeepJob,
    ResearchFastJob,
    Verification,
)
from app.db import tables
from app.research import events as ev
from app.research.events import EventLog, LeakDetected, LeakGuard
from app.research.fake import (
    FAKE_URL,
    fake_deep_findings,
    fake_fast_pass_output,
)
from app.research.jobs import (
    FastPassError,
    ResearchDeps,
    handle_research_deep,
    handle_research_fast,
)
from app.research.models import DeepFindings, FastPassOutput

from research.fakes import FakeResearchDB, fake_deps

pytestmark = pytest.mark.asyncio

SECRET = fake_fast_pass_output().sensitive_values[0].value


def deps(**overrides: Any) -> ResearchDeps:
    return dataclasses.replace(fake_deps(), **overrides)


def fast_job(
    store: FakeResearchDB, pages: list[tuple[str, bytes]] | None = None
) -> tables.Job:
    store.add_document(pages or [("image/jpeg", b"p1")])
    payload = ResearchFastJob(
        case_id="case_1", user_id="user_1", document_ids=["doc_1"], user_language="es"
    )
    return store.add_claimed_job(payload, "case_1")


async def deep_job(
    store: FakeResearchDB, short_goal: str | None = "Confirm your form was received"
) -> tables.Job:
    out = fake_fast_pass_output("case_1")
    await store.create_case("case_1", "user_1", ["doc_1"])
    await store.save_fast_result("case_1", out.r1)
    payload = ResearchDeepJob(
        case_id="case_1",
        user_id="user_1",
        document_ids=["doc_1"],
        signals=out.signals.model_copy(update={"county": "Signal County"}),
        call_purpose=out.call_purpose,
        call_goal_short_en=short_goal,
    )
    return store.add_claimed_job(payload, "case_1")


# --- research_fast ---


async def test_fast_happy_path(store: FakeResearchDB) -> None:
    seen: list[Any] = []

    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        seen.extend(blocks)
        return fake_fast_pass_output(case_id)

    pages = [("image/jpeg", f"page{i}".encode()) for i in range(3)]
    job = fast_job(store, pages)
    await handle_research_fast(job, deps(fast_pass_fn=fast))

    assert job.status == "done"
    r1 = FastResult.model_validate(job.result)
    assert r1.status == "ok"
    assert store.cases["case_1"].fast_result == job.result
    assert [b["source"]["data"] for b in seen] == ["cGFnZTA=", "cGFnZTE=", "cGFnZTI="]
    assert store.case_refs == {("case_1", "case_number"): SECRET}
    assert store.job_types() == ["research_fast", "memory_write", "research_deep"]
    memory = next(j for j in store.jobs.values() if j.type == "memory_write")
    assert memory.payload["source"] == "from_document"
    assert memory.payload["source_ref"] == "doc_1"
    deep = next(j for j in store.jobs.values() if j.type == "research_deep")
    assert deep.payload["call_purpose"] == "Confirm the form was received"
    assert deep.payload["call_goal_short_en"] == "Confirm your form was received"
    assert deep.payload["signals"] == fake_fast_pass_output().signals.model_dump(
        mode="json"
    )
    assert deep.created_by == "research_agent" and deep.user_id == "user_1"
    assert store.event_types() == [ev.FAST_STARTED, ev.CASE_CREATED, ev.FAST_DONE]
    assert store.events[-1].data == {
        "status": "ok",
        "doc_type": "generic_agency_notice",
    }
    assert all(e.source == "research_agent" for e in store.events)
    assert all(e.user_id == "user_1" and e.job_id == job.id for e in store.events)


async def test_fast_rerun_reuses_the_case(store: FakeResearchDB) -> None:
    await store.create_case("case_1", "user_1", ["doc_1"])
    job = fast_job(store)
    await handle_research_fast(job, deps())

    assert job.status == "done"
    assert ev.CASE_CREATED not in store.event_types()


async def test_fast_needs_better_image_queues_no_deep(store: FakeResearchDB) -> None:
    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        out = fake_fast_pass_output(case_id)
        r1 = FastResult(
            case_id=case_id, status="needs_better_image", image_issue="Too blurry"
        )
        return out.model_copy(update={"r1": r1, "sensitive_values": []})

    job = fast_job(store)
    await handle_research_fast(job, deps(fast_pass_fn=fast))

    assert job.result["status"] == "needs_better_image"
    assert "research_deep" not in store.job_types()
    # The case holds the R1, so its stage reads needs_better_image.
    assert store.cases["case_1"].fast_result["status"] == "needs_better_image"


async def test_unsupported_media_becomes_needs_better_image(
    store: FakeResearchDB,
) -> None:
    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise AssertionError("fast pass must not run")

    job = fast_job(store, [("image/heic", b"x")])
    await handle_research_fast(job, deps(fast_pass_fn=fast))

    r1 = FastResult.model_validate(job.result)
    assert r1.status == "needs_better_image"
    assert r1.image_issue and "JPG" in r1.image_issue
    assert store.job_types() == ["research_fast"]


async def test_missing_document_fails_job(store: FakeResearchDB) -> None:
    payload = ResearchFastJob(
        case_id="case_1", user_id="user_1", document_ids=["doc_x"], user_language="es"
    )
    job = store.add_claimed_job(payload, "case_1")
    with pytest.raises(ValueError):
        await handle_research_fast(job, deps())
    assert job.status == "failed"
    assert store.event_types()[-1] == ev.FAST_FAILED


async def test_slow_fast_pass_emits_fast_slow_then_succeeds(
    store: FakeResearchDB,
) -> None:
    async def fast(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        await asyncio.sleep(0.05)
        return fake_fast_pass_output(case_id)

    job = fast_job(store)
    await handle_research_fast(
        job, deps(fast_pass_fn=fast, fast_slow_s=0.01, fast_cap_s=1.0)
    )

    assert job.status == "done"
    assert store.event_types() == [
        ev.FAST_STARTED,
        ev.FAST_SLOW,
        ev.CASE_CREATED,
        ev.FAST_DONE,
    ]


async def test_fast_pass_over_hard_cap_fails_job(store: FakeResearchDB) -> None:
    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        await asyncio.sleep(1)
        raise AssertionError("should have been cancelled")

    job = fast_job(store)
    await handle_research_fast(
        job, deps(fast_pass_fn=fast, fast_slow_s=0.01, fast_cap_s=0.05)
    )

    assert job.status == "failed"
    assert "exceeded" in (job.error or "")
    assert store.event_types() == [ev.FAST_STARTED, ev.FAST_SLOW, ev.FAST_FAILED]
    assert store.cases == {}


async def test_fast_pass_error_fails_job_with_event(store: FakeResearchDB) -> None:
    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise FastPassError("model refused")

    job = fast_job(store)
    await handle_research_fast(job, deps(fast_pass_fn=fast))

    assert job.status == "failed"
    assert store.event_types() == [ev.FAST_STARTED, ev.FAST_FAILED]
    assert store.job_types() == ["research_fast"]


async def test_unexpected_error_fails_job_then_propagates(
    store: FakeResearchDB,
) -> None:
    async def fast(*_: Any, **__: Any) -> FastPassOutput:
        raise KeyError("bug")

    job = fast_job(store)
    with pytest.raises(KeyError):
        await handle_research_fast(job, deps(fast_pass_fn=fast))
    assert job.status == "failed"
    assert store.event_types()[-1] == ev.FAST_FAILED


# --- research_deep ---


async def test_deep_happy_path(store: FakeResearchDB) -> None:
    job = await deep_job(store)
    await handle_research_deep(job, deps())

    r2 = DeepResult.model_validate(job.result)
    assert r2.call_recommended is True
    assert r2.verification.status == "verified"
    assert r2.verification.evidence[0] == FAKE_URL
    [(ver_id, verification)] = store.verifications.items()
    assert verification.case_id == "case_1" and verification.official_phone
    brief = store.case_briefs[r2.brief_id]
    assert brief.brief["brief_id"] == r2.brief_id
    assert all(rule in brief.brief["must_not_do"] for rule in REQUIRED_MUST_NOT_DO)
    assert brief.brief["call_goal_en"] and brief.handoff_note
    assert store.event_types() == [
        ev.DEEP_STARTED,
        ev.SEARCH,
        ev.FETCH,
        ev.CHECK,
        ev.VERIFIED,
        ev.DEEP_DONE,
    ]
    assert store.events[4].data == {
        "ver_id": ver_id,
        "red_flag_count": 0,
        "source": "example.gov",
    }


async def test_r2_gets_the_short_goal_and_the_brief_keeps_the_full_one(
    store: FakeResearchDB,
) -> None:
    job = await deep_job(store)
    await handle_research_deep(job, deps())

    r2 = DeepResult.model_validate(job.result)
    assert r2.call_goal_en == "Confirm your form was received"
    brief = store.case_briefs[r2.brief_id].brief
    assert brief["call_goal_en"] == fake_deep_findings().call_goal_en
    assert brief["call_goal_en"] != r2.call_goal_en


async def test_deep_job_without_a_short_goal_leaves_r2_goal_empty(
    store: FakeResearchDB,
) -> None:
    job = await deep_job(store, short_goal=None)
    await handle_research_deep(job, deps())

    r2 = DeepResult.model_validate(job.result)
    assert r2.call_goal_en is None
    assert store.case_briefs[r2.brief_id].brief["call_goal_en"]


async def test_deep_puts_the_official_source_first(store: FakeResearchDB) -> None:
    async def deep(*_: Any, **__: Any) -> DeepFindings:
        findings = fake_deep_findings()
        verification = findings.verification.model_copy(
            update={"evidence": ["The number is on the issuer's page", FAKE_URL]}
        )
        return findings.model_copy(update={"verification": verification})

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=deep))

    [verification] = store.verifications.values()
    assert verification.result["evidence"] == [
        FAKE_URL,
        "The number is on the issuer's page",
    ]


async def test_deep_suspicious_has_no_brief_and_no_call(store: FakeResearchDB) -> None:
    async def deep(*_: Any, **__: Any) -> DeepFindings:
        return DeepFindings(
            verification=Verification(
                status="suspicious",
                official_phone=None,
                letter_phone_matches=None,
                evidence=[],
                red_flags=["Demands payment by gift card"],
            )
        )

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=deep))

    r2 = DeepResult.model_validate(job.result)
    assert r2.call_recommended is False and r2.brief_id is None
    assert store.case_briefs == {}
    verdict = next(e for e in store.events if e.type == ev.SUSPICIOUS)
    assert verdict.data["red_flag_count"] == 1
    assert "source" not in verdict.data


@pytest.mark.parametrize("failure", ["timeout", "network"])
async def test_deep_failure_finishes_with_unknown(
    store: FakeResearchDB, failure: str
) -> None:
    async def deep(*_: Any, **__: Any) -> DeepFindings:
        if failure == "network":
            raise httpx.ConnectError("down")
        await asyncio.sleep(1)
        raise AssertionError("should have been cancelled")

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=deep, deep_timeout_s=0.02))

    assert job.status == "done"
    r2 = DeepResult.model_validate(job.result)
    assert r2.verification.status == "unknown"
    assert r2.verification.evidence and r2.call_recommended is False
    assert store.event_types() == [
        ev.DEEP_STARTED,
        ev.DEEP_FAILED,
        ev.UNKNOWN,
        ev.DEEP_DONE,
    ]


async def test_deep_programming_error_fails_loudly(store: FakeResearchDB) -> None:
    async def deep(*_: Any, **__: Any) -> DeepFindings:
        raise TypeError("bug")

    job = await deep_job(store)
    with pytest.raises(TypeError):
        await handle_research_deep(job, deps(deep_pass_fn=deep))
    assert job.status == "failed"
    assert store.event_types()[-1] == ev.DEEP_FAILED


async def test_deep_reads_county_from_the_job_signals(store: FakeResearchDB) -> None:
    seen: dict[str, Any] = {}

    async def deep(
        signals: Any, call_purpose: Any, county: Any, **_: Any
    ) -> DeepFindings:
        seen.update(county=county, call_purpose=call_purpose)
        return fake_deep_findings()

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=deep))
    assert seen == {
        "county": "Signal County",
        "call_purpose": "Confirm the form was received",
    }


async def test_doc_type_passed_only_when_accepted(store: FakeResearchDB) -> None:
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

    await handle_research_deep(await deep_job(store), deps(deep_pass_fn=with_doc_type))
    assert seen["doc_type"] == "generic_agency_notice"

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=without_doc_type))
    assert job.status == "done"


async def test_log_fn_events_land_in_events(store: FakeResearchDB) -> None:
    async def deep(*_: Any, log: Any, **__: Any) -> DeepFindings:
        await log(ev.FETCH, "Fetched a page", {"url": "https://www.example.gov/"})
        return fake_deep_findings()

    job = await deep_job(store)
    await handle_research_deep(job, deps(deep_pass_fn=deep))

    fetch = next(e for e in store.events if e.type == ev.FETCH)
    assert fetch.data == {"url": "https://www.example.gov/"}
    assert fetch.job_id == job.id and fetch.case_id == "case_1"


# --- Leak guard ---


async def test_leak_in_job_result_raises_and_fails_job(store: FakeResearchDB) -> None:
    async def leaky(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        out = fake_fast_pass_output(case_id)
        r1 = out.r1.model_copy(update={"explanation_en": f"Your case is {SECRET}."})
        return out.model_copy(update={"r1": r1})

    job = fast_job(store)
    with pytest.raises(LeakDetected):
        await handle_research_fast(job, deps(fast_pass_fn=leaky))

    assert job.status == "failed"
    assert store.event_types()[-1] == ev.FAST_FAILED
    written = json.dumps(
        [e.model_dump(mode="json") for e in store.events]
        + [j.model_dump(mode="json") for j in store.jobs.values()]
        + [c.model_dump(mode="json") for c in store.cases.values()],
        default=str,
    )
    assert SECRET not in written


async def test_leak_in_event_raises_before_write(store: FakeResearchDB) -> None:
    guard = LeakGuard()
    guard.add([SECRET])
    log = EventLog(guard, user_id="user_1", case_id="case_1", job_id="job_1")

    with pytest.raises(LeakDetected) as exc:
        await log.emit(ev.CHECK, "checked", {"note": f"saw {SECRET}"})
    assert SECRET not in str(exc.value)
    assert store.events == []


async def test_guard_matches_short_values_only_as_whole_words() -> None:
    guard = LeakGuard()
    guard.add(["Ana", 'O"Neil Street 12'])

    guard.check("event", {"summary_en": "Analysis of the notice, Banana"})
    for leaked in ("Hello Ana.", "hello ANA", {"note": 'at O"Neil Street 12'}):
        with pytest.raises(LeakDetected):
            guard.check("event", leaked)


async def test_fast_passes_the_users_note_through(store: FakeResearchDB) -> None:
    notes: list[str | None] = []

    async def fast(blocks: list[Any], *, case_id: str, **kwargs: Any) -> FastPassOutput:
        notes.append(kwargs.get("user_note_en"))
        return fake_fast_pass_output(case_id)

    store.add_document([("image/jpeg", b"p1")])
    payload = ResearchFastJob(
        case_id="case_1",
        user_id="user_1",
        document_ids=["doc_1"],
        user_language="es",
        user_note_en="The one from USCIS",
    )
    job = store.add_claimed_job(payload, "case_1")
    await handle_research_fast(job, deps(fast_pass_fn=fast))
    assert notes == ["The one from USCIS"]
