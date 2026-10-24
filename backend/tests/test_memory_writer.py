"""The memory writer (Goal 7.1–7.4, 7.6) on fakes: no Anthropic, no database."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from app.contracts import (
    Component,
    EventType,
    FactSource,
    FactStatus,
    JobStatus,
    JobType,
    MemoryWriteJob,
    MessageDirection,
    MessageSender,
    ProposedFact,
    Sensitivity,
)
from app.db import tables
from app.memory.extract import (
    ExtractedFact,
    ExtractedProfile,
    Extraction,
    ExtractionError,
    FactExtractor,
)
from app.memory.filters import Candidate, storable
from app.memory.worker import MemoryWorker
from app.memory.writer import MemoryDeps
from whatsapp_fakes import FakeDB, use_spanish

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


class FakeExtractor:
    def __init__(self, extraction: Extraction | None = None, fail: bool = False):
        self.extraction = extraction or Extraction(facts=[], profile=ExtractedProfile())
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def extract(
        self, text_en: str, previous_reply_en: str | None, known_facts: list[str]
    ) -> Extraction:
        self.calls.append(
            {"text": text_en, "previous": previous_reply_en, "known": known_facts}
        )
        if self.fail:
            raise ExtractionError("extraction failed (APITimeoutError)")
        return self.extraction


@pytest.fixture
def jobs_db(db: FakeDB, monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    monkeypatch.setattr("app.db.jobs.claim_next", db.claim_next)
    monkeypatch.setattr("app.db.jobs.finish", db.finish)
    monkeypatch.setattr("app.db.jobs.fail", db.fail)
    return db


def worker(extractor: FakeExtractor | None) -> MemoryWorker:
    fake: Any = extractor
    return MemoryWorker(MemoryDeps(extractor=fake))


async def said(db: FakeDB, user: tables.User, text_en: str) -> tables.Message:
    """A reply from the assistant, then the user's message, as the pipe logs them."""
    await db.append_message(
        user.id,
        MessageDirection.OUT,
        MessageSender.ORCHESTRATOR,
        "¿Cuántas personas viven con usted?",
        "es",
        body_en="How many people live with you?",
    )
    return await db.append_message(
        user.id, MessageDirection.IN, MessageSender.USER, text_en, "es", body_en=text_en
    )


async def queue(db: FakeDB, user: tables.User, job: MemoryWriteJob) -> tables.Job:
    return await db.enqueue(job, Component.ORCHESTRATOR, user.id)


def user_said(user: tables.User, message: tables.Message) -> MemoryWriteJob:
    return MemoryWriteJob(
        user_id=user.id,
        source=FactSource.USER_SAID,
        source_ref=message.id,
        proposed_facts=[],
    )


def stored(db: FakeDB) -> dict[str, tables.Fact]:
    return {fact.fact: fact for fact in db.facts}


async def test_user_message_facts_are_filtered_held_and_saved(
    jobs_db: FakeDB,
) -> None:
    db = jobs_db
    user = await use_spanish(db)
    message = await said(db, user, "We are three. I fled Guatemala ...")
    job = await queue(db, user, user_said(user, message))
    extractor = FakeExtractor(
        Extraction(
            facts=[
                ExtractedFact(fact="Has two children", category="household"),
                ExtractedFact(fact="Lives in Fresno County", category="contact"),
                ExtractedFact(
                    fact="Has an asylum interview on Nov 18", category="other"
                ),
                ExtractedFact(fact="Gets paid in cash", category="income"),
                ExtractedFact(fact="Is diabetic", category="health"),
                # C34: claim details and identifiers are never stored, whatever
                # the model called them.
                ExtractedFact(
                    fact="Fled Guatemala because of gangs", category="household"
                ),
                ExtractedFact(fact="Is a citizen of Honduras", category="other"),
                ExtractedFact(fact="A-Number is A123456789", category="other"),
                ExtractedFact(fact="Phone is 510 555 0123", category="contact"),
                ExtractedFact(fact="Religion is the reason", category="asylum_claim"),
            ],
            profile=ExtractedProfile(
                county="Fresno County", household_size=3, contact_preference=None
            ),
        )
    )

    assert await worker(extractor).drain() == 1

    facts = stored(db)
    assert set(facts) == {
        "Has two children",
        "Lives in Fresno County",
        "Has an asylum interview on Nov 18",
        "Gets paid in cash",
        "Is diabetic",
    }
    for text in ("Has two children", "Lives in Fresno County"):
        assert facts[text].status == FactStatus.ACTIVE
        assert facts[text].sensitivity == Sensitivity.NORMAL
    interview = facts["Has an asylum interview on Nov 18"]
    assert (interview.category, interview.status) == (
        "immigration",
        FactStatus.PENDING_CONSENT,
    )
    for text in ("Gets paid in cash", "Is diabetic"):
        assert facts[text].sensitivity == Sensitivity.SENSITIVE
        assert facts[text].status == FactStatus.PENDING_CONSENT
    assert all(f.source == FactSource.USER_SAID for f in db.facts)
    assert all(f.source_ref == message.id for f in db.facts)
    assert db.profiles[user.id].fields == {"county": "Fresno", "household_size": "3"}

    done = db.jobs[job.id]
    assert done.status == JobStatus.DONE
    assert done.result["dropped"] == 5
    assert len(done.result["saved"]) == 2
    assert len(done.result["pending_consent"]) == 3
    assert extractor.calls[0]["previous"] == "How many people live with you?"


async def test_events_carry_fact_ids_never_fact_text(jobs_db: FakeDB) -> None:
    db = jobs_db
    user = await use_spanish(db)
    message = await said(db, user, "I have two kids and an asylum interview")
    await queue(db, user, user_said(user, message))
    extractor = FakeExtractor(
        Extraction(
            facts=[
                ExtractedFact(fact="Has two children", category="household"),
                ExtractedFact(fact="Has an asylum interview", category="immigration"),
            ],
            profile=ExtractedProfile(),
        )
    )

    await worker(extractor).drain()

    by_fact = {f.id: f for f in db.facts}
    assert db.event_types() == [
        EventType.MEMORY_FACT_SAVED,
        EventType.MEMORY_FACT_PENDING_CONSENT,
    ]
    for event in db.events:
        assert set(event.data) == {"fact_id"}
        assert event.data["fact_id"] in by_fact
        assert event.source == Component.MEMORY_WRITER
        assert "children" not in event.summary_en
        assert "asylum" not in event.summary_en


async def test_proposed_facts_keep_their_source_and_immigration_is_held(
    jobs_db: FakeDB,
) -> None:
    db = jobs_db
    user = await use_spanish(db)
    job = await queue(
        db,
        user,
        MemoryWriteJob(
            user_id=user.id,
            source=FactSource.FROM_DOCUMENT,
            source_ref="doc_1",
            proposed_facts=[
                ProposedFact(
                    fact="Has two children on the asylum application",
                    source=FactSource.FROM_DOCUMENT,
                    sensitivity=Sensitivity.SENSITIVE,
                ),
                # Marked normal by mistake: still immigration, still held.
                ProposedFact(
                    fact="Has an asylum interview scheduled",
                    source=FactSource.FROM_DOCUMENT,
                ),
                ProposedFact(
                    fact="Country of nationality is Venezuela",
                    source=FactSource.FROM_DOCUMENT,
                ),
            ],
        ),
    )

    # Proposed facts need no model call, so no extractor either.
    await worker(None).drain()

    facts = stored(db)
    assert set(facts) == {
        "Has two children on the asylum application",
        "Has an asylum interview scheduled",
    }
    for fact in facts.values():
        assert fact.category == "immigration"
        assert fact.status == FactStatus.PENDING_CONSENT
        assert (fact.source, fact.source_ref) == (FactSource.FROM_DOCUMENT, "doc_1")
    assert db.jobs[job.id].result["dropped"] == 1


async def test_the_contract_fixture_from_a_call_is_held_for_consent(
    jobs_db: FakeDB,
) -> None:
    """Plan.md's own example sends no sensitivity, so it arrives `normal`; it's
    still an immigration fact and must wait for the user's OK (C34)."""
    db = jobs_db
    user = await use_spanish(db)
    payload = json.loads((FIXTURES / "memory_write_job.json").read_text("utf-8"))
    payload["user_id"] = user.id
    job = await queue(db, user, MemoryWriteJob.model_validate(payload))

    await worker(None).drain()

    [fact] = db.facts
    assert (fact.fact, fact.category) == (
        "Asylum interview confirmed for Nov 18",
        "immigration",
    )
    assert (fact.sensitivity, fact.status) == (
        Sensitivity.SENSITIVE,
        FactStatus.PENDING_CONSENT,
    )
    assert (fact.source, fact.source_ref) == (FactSource.FROM_CALL, "call_5")
    assert db.jobs[job.id].status == JobStatus.DONE
    assert db.event_types() == [EventType.MEMORY_FACT_PENDING_CONSENT]


async def test_known_and_repeated_facts_are_not_saved_twice(jobs_db: FakeDB) -> None:
    db = jobs_db
    user = await use_spanish(db)
    await db.add_fact(
        user.id,
        "Has two children",
        "household",
        FactSource.USER_SAID,
        Sensitivity.NORMAL,
        FactStatus.ACTIVE,
    )
    message = await said(db, user, "Two kids. Prefer voice notes.")
    job = await queue(db, user, user_said(user, message))
    extractor = FakeExtractor(
        Extraction(
            facts=[
                ExtractedFact(fact="has two children.", category="household"),
                ExtractedFact(fact="Prefers voice notes", category="contact"),
                ExtractedFact(fact="Prefers  voice notes!", category="contact"),
            ],
            profile=ExtractedProfile(contact_preference="voice notes"),
        )
    )

    await worker(extractor).drain()

    assert [f.fact for f in db.facts] == ["Has two children", "Prefers voice notes"]
    assert db.jobs[job.id].result["duplicates"] == 2
    assert extractor.calls[0]["known"] == ["Has two children"]
    assert db.profiles[user.id].fields == {"contact_preference": "voice notes"}


async def test_backlog_drains_and_every_job_ends_done_or_failed(
    jobs_db: FakeDB,
) -> None:
    db = jobs_db
    user = await use_spanish(db)
    number = await said(db, user, "1")
    words = await said(db, user, "I have two kids")
    queued = [
        await queue(db, user, user_said(user, number)),  # no words: skipped
        await queue(
            db,
            user,
            MemoryWriteJob(
                user_id=user.id,
                source=FactSource.USER_SAID,
                source_ref="msg_deleted",  # deleted from the dashboard since
                proposed_facts=[],
            ),
        ),
        await queue(db, user, user_said(user, words)),  # the model call fails
        await queue(
            db,
            user,
            MemoryWriteJob(
                user_id=user.id,
                source=FactSource.FROM_CALL,
                source_ref="call_1",
                proposed_facts=[
                    ProposedFact(
                        fact="Asylum interview confirmed for Nov 18",
                        source=FactSource.FROM_CALL,
                        sensitivity=Sensitivity.SENSITIVE,
                    )
                ],
            ),
        ),
    ]
    extractor = FakeExtractor(fail=True)
    memory = worker(extractor)

    assert await memory.drain() == 4
    assert await memory.drain() == 0

    statuses = [db.jobs[j.id].status for j in queued]
    assert statuses == [
        JobStatus.DONE,
        JobStatus.DONE,
        JobStatus.FAILED,
        JobStatus.DONE,
    ]
    assert db.jobs[queued[0].id].result["skipped"] == "no words"
    assert db.jobs[queued[1].id].result["skipped"] == "message not found"
    assert len(extractor.calls) == 1  # "1" never reached the model
    assert [f.fact for f in db.facts] == ["Asylum interview confirmed for Nov 18"]
    assert all(
        j.status in (JobStatus.DONE, JobStatus.FAILED)
        for j in db.jobs_of(JobType.MEMORY_WRITE)
    )


async def test_user_said_without_an_extractor_fails_the_job(jobs_db: FakeDB) -> None:
    db = jobs_db
    user = await use_spanish(db)
    message = await said(db, user, "I have two kids")
    job = await queue(db, user, user_said(user, message))

    await worker(None).drain()

    assert db.jobs[job.id].status == JobStatus.FAILED
    assert db.facts == []


@pytest.mark.parametrize(
    "fact",
    [
        "Fled El Salvador in 2019",
        "Is afraid to go back",
        "Came from Afghanistan",
        "Receipt number is ZLA1234567890",
        "Social Security number ends in 1234",
        "Can be reached at 510-555-0123",
        "Email is ana@example.com",
        "Date of birth is March 3",
        "Lives at <ref:address>",
    ],
)
def test_claim_details_and_identifiers_are_never_storable(fact: str) -> None:
    assert storable(Candidate(fact, "other", FactSource.USER_SAID)) is None


@pytest.mark.parametrize(
    ("fact", "status"),
    [
        ("Interview on 2026-11-18 at 8:30", FactStatus.PENDING_CONSENT),
        ("Has a hearing at immigration court", FactStatus.PENDING_CONSENT),
        ("Prefers text messages", FactStatus.ACTIVE),
        ("Has three children", FactStatus.ACTIVE),
    ],
)
def test_dates_survive_and_immigration_is_always_held(
    fact: str, status: FactStatus
) -> None:
    result = storable(Candidate(fact, "other", FactSource.USER_SAID))
    assert result is not None
    assert result.status == status


class FakeParseClient:
    def __init__(self, parsed: Extraction | None = None, fail: bool = False):
        self.messages = self
        self.requests: list[dict[str, Any]] = []
        self._parsed = parsed
        self._fail = fail

    async def parse(self, **request: Any) -> Any:
        self.requests.append(request)
        if self._fail:
            raise anthropic.APITimeoutError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        return SimpleNamespace(parsed_output=self._parsed)


async def test_extractor_sends_the_message_as_data_with_its_context() -> None:
    parsed = Extraction(facts=[], profile=ExtractedProfile())
    client = FakeParseClient(parsed)
    fake: Any = client
    extractor = FactExtractor(fake, "model-fast")

    result = await extractor.extract(
        "Three of us", "How many people live with you?", ["Has two children"]
    )

    assert result == parsed
    request = client.requests[0]
    assert request["model"] == "model-fast"
    assert request["output_format"] is Extraction
    content = request["messages"][0]["content"]
    assert "<message>\nThree of us\n</message>" in content
    assert "How many people live with you?" in content
    assert "- Has two children" in content


async def test_extractor_failures_raise_extraction_error() -> None:
    fake: Any = FakeParseClient(fail=True)
    with pytest.raises(ExtractionError):
        await FactExtractor(fake, "model-fast").extract("hi", None, [])
    empty: Any = FakeParseClient(parsed=None)
    with pytest.raises(ExtractionError):
        await FactExtractor(empty, "model-fast").extract("hi", None, [])
