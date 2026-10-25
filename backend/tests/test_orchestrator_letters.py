"""Letters to research (Goal 4.2), noticing finished jobs (4.3), and the orchestrator
turn running outside the per-number lock (concern 8), on fakes."""

import asyncio

import pytest
from app.contracts import (
    AskUserRequest,
    Component,
    EventType,
    FastResult,
    JobStatus,
    JobType,
    ResearchFastJob,
)
from app.db import tables
from app.orchestrator.conversation import Conversation
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letter_result import LetterResults
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.relay.ask_user import AskUser
from whatsapp_fakes import FakeDB, FakeWhatsApp, inbound, use_spanish, wait_for_batches


async def send_letter(pipe: InboundPipe, photos: int = 1) -> None:
    for _ in range(photos):
        await pipe.handle(inbound(photos=1))
    await wait_for_batches()


async def settle() -> None:
    """Give the job watchers (polling every 10 ms) time to react."""
    await asyncio.sleep(0.1)


def fast_payloads(db: FakeDB) -> list[ResearchFastJob]:
    return [
        ResearchFastJob.model_validate(j.payload)
        for j in db.jobs_of(JobType.RESEARCH_FAST)
    ]


# 4.2: letter → research_fast


async def test_letter_queues_the_fast_pass_with_a_new_case(
    pipe: InboundPipe, db: FakeDB
) -> None:
    user = await use_spanish(db)

    await send_letter(pipe, photos=2)

    [document] = db.documents
    [job] = db.jobs_of(JobType.RESEARCH_FAST)
    [payload] = fast_payloads(db)
    assert payload.case_id.startswith("case_")
    assert (job.case_id, job.user_id, job.created_by) == (
        payload.case_id,
        user.id,
        "orchestrator",
    )
    assert payload.document_ids == [document.id]
    assert payload.user_language == "es"


async def test_photo_while_research_is_reading_asks_same_or_new(
    pipe: InboundPipe, db: FakeDB
) -> None:
    """Research creates the case row only when the fast pass finishes; the question
    must come before that (concern 1)."""
    await use_spanish(db)
    await send_letter(pipe)
    assert db.cases == []

    await pipe.handle(inbound(photos=1))

    assert db.outbound_templates() == ["letter.received", "letter.same_or_new"]


async def test_same_letter_while_queued_needs_no_second_job(
    pipe: InboundPipe, db: FakeDB
) -> None:
    await use_spanish(db)
    await send_letter(pipe)

    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound("1"))

    [document] = db.documents
    assert len(document.pages) == 2
    # Research hasn't claimed the job: it will read both pages anyway.
    assert len(db.jobs_of(JobType.RESEARCH_FAST)) == 1


async def test_same_letter_after_research_started_reruns_the_fast_pass(
    pipe: InboundPipe, db: FakeDB
) -> None:
    await use_spanish(db)
    await send_letter(pipe)
    [first] = db.jobs_of(JobType.RESEARCH_FAST)
    first.status = JobStatus.RUNNING

    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound("1"))

    old, new = fast_payloads(db)
    assert new.case_id == old.case_id
    assert new.document_ids == old.document_ids


async def test_pages_added_to_an_active_case_rerun_in_that_case(
    pipe: InboundPipe, db: FakeDB
) -> None:
    user = await use_spanish(db)
    letter = await db.create_document(user.id, ["media_old"])
    case = tables.Case(user_id=user.id, document_ids=[letter.id])
    db.cases.append(case)

    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound("1"))

    [payload] = fast_payloads(db)
    assert (payload.case_id, payload.document_ids) == (case.id, [letter.id])


async def test_photo_after_an_unreadable_letter_starts_a_new_letter(
    pipe: InboundPipe, db: FakeDB
) -> None:
    """No case row after `needs_better_image`, and research is done reading."""
    await use_spanish(db)
    await send_letter(pipe)
    [job] = db.jobs_of(JobType.RESEARCH_FAST)
    db.finish_job(job.id)
    await settle()

    await pipe.handle(inbound(photos=1))

    assert db.outbound_templates() == ["letter.received", "letter.received"]


# 4.3: noticing finished jobs


async def test_slow_fast_pass_says_its_taking_longer_once(
    whatsapp: FakeWhatsApp,
    job_watcher: JobWatcher,
    letter_results: LetterResults,
    conversation: Conversation,
    db: FakeDB,
) -> None:
    user = await use_spanish(db)
    letters = Letters(
        whatsapp,
        job_watcher,
        letter_results,
        slow_after_s=0.05,
        conversation=conversation,
    )

    await letters.start(user.id, "doc_1")
    await asyncio.sleep(0.2)

    assert db.outbound_templates() == ["research.slow"]
    [job] = db.jobs_of(JobType.RESEARCH_FAST)
    assert db.messages[-1].case_id == job.case_id

    db.finish_job(job.id)
    await settle()
    assert not job_watcher.is_watching(job.id)
    assert db.outbound_templates() == ["research.slow"]


async def test_user_sees_typing_while_the_fast_pass_reads_the_letter(
    pipe: InboundPipe,
    whatsapp: FakeWhatsApp,
    conversation: Conversation,
    job_watcher: JobWatcher,
    db: FakeDB,
) -> None:
    """ "Typing…" on the last photo, refreshed until the result; no message, no
    row."""
    user = await use_spanish(db)
    photo = inbound(photos=1)
    await pipe.handle(photo)
    await wait_for_batches()
    await asyncio.sleep(0.1)  # a few refreshes

    assert conversation.is_typing(user.id)
    assert len(whatsapp.typing_sids) >= 2
    assert set(whatsapp.typing_sids) == {photo.message_sid}
    assert db.outbound_templates() == ["letter.received"]

    [job] = db.jobs_of(JobType.RESEARCH_FAST)
    db.finish_job(job.id)
    await settle()
    assert not conversation.is_typing(user.id)
    pings = len(whatsapp.typing_sids)
    await asyncio.sleep(0.1)
    assert len(whatsapp.typing_sids) == pings


async def test_typing_stops_at_its_cap(
    whatsapp: FakeWhatsApp, conversation: Conversation
) -> None:
    conversation.heard("user_1", "SM9")
    conversation.typing("user_1", "lookup", max_s=0.05)
    await asyncio.sleep(0.15)

    assert not conversation.is_typing("user_1")
    pings = len(whatsapp.typing_sids)
    assert pings >= 1
    await asyncio.sleep(0.1)
    assert len(whatsapp.typing_sids) == pings


async def test_typing_shows_while_any_reason_is_open(
    whatsapp: FakeWhatsApp, conversation: Conversation
) -> None:
    conversation.heard("user_1", "SM9")
    conversation.typing("user_1", "turn", max_s=5)
    conversation.typing("user_1", "lookup", max_s=5)

    conversation.done_typing("user_1", "turn")
    assert conversation.is_typing("user_1")
    conversation.done_typing("user_1", "lookup")
    assert not conversation.is_typing("user_1")


async def test_stale_fast_pass_is_ignored(
    letters: Letters, job_watcher: JobWatcher, db: FakeDB
) -> None:
    user = await use_spanish(db)
    await letters.start(user.id, "doc_1")
    [old] = db.jobs_of(JobType.RESEARCH_FAST)
    old.status = JobStatus.RUNNING
    await letters.pages_added(user, "doc_1")
    _, new = db.jobs_of(JobType.RESEARCH_FAST)

    db.finish_job(old.id)
    await settle()

    # Still reading: the newer job hasn't finished.
    assert await letters.active_letter(user.id) == "doc_1"
    db.finish_job(new.id)
    await settle()
    assert await letters.active_letter(user.id) is None


async def test_watcher_reports_a_failed_job_once(
    job_watcher: JobWatcher, db: FakeDB
) -> None:
    user = await use_spanish(db)
    job = await db.enqueue(
        ResearchFastJob(
            case_id="case_1",
            user_id=user.id,
            document_ids=["doc_1"],
            user_language="es",
        ),
        Component.ORCHESTRATOR,
        user.id,
        "case_1",
    )
    finished: list[tables.Job] = []

    async def on_finished(done: tables.Job) -> None:
        finished.append(done)

    job_watcher.watch(job.id, on_finished)
    job_watcher.watch(job.id, on_finished)
    db.fail_job(job.id, "fast pass failed (FastPassError)")
    await settle()

    [done] = finished
    assert (done.id, done.status, done.error) == (
        job.id,
        JobStatus.FAILED,
        "fast pass failed (FastPassError)",
    )


async def test_watcher_stops_when_the_job_is_gone(
    job_watcher: JobWatcher, db: FakeDB
) -> None:
    async def on_finished(done: tables.Job) -> None:
        pytest.fail("a missing job never finishes")

    job_watcher.watch("job_missing", on_finished)
    await settle()

    assert not job_watcher.is_watching("job_missing")


# Concern 8: a slow turn doesn't hold up an ask_user reply


async def test_ask_user_reply_does_not_wait_behind_a_slow_turn(
    pipe: InboundPipe,
    ask_user: AskUser,
    db: FakeDB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await use_spanish(db)
    call = db.add_call(user)
    release = asyncio.Event()

    async def slow_turn(*_: object, **__: object) -> None:
        await release.wait()

    monkeypatch.setattr(pipe, "_turn", slow_turn)
    turn = asyncio.create_task(pipe.handle(inbound("¿qué dice mi carta?")))
    await asyncio.sleep(0.01)

    asking = asyncio.create_task(
        ask_user.ask(
            AskUserRequest(
                question_id="question_1",
                call_id=call.id,
                template="menu_choice",
                options_en=["Appointment", "Case status"],
                default_option=1,
                timeout_s=5,
            )
        )
    )
    while EventType.CALL_ASK_USER not in db.event_types():
        await asyncio.sleep(0.01)
    await asyncio.wait_for(pipe.handle(inbound("2")), timeout=1)

    assert (await asyncio.wait_for(asking, timeout=1)).choice == 2
    assert not turn.done()
    release.set()
    await turn


# C39: research asks which letter to read


async def test_answer_to_research_question_reruns_the_fast_pass_with_the_note(
    pipe: InboundPipe, db: FakeDB
) -> None:
    await use_spanish(db)
    await send_letter(pipe, photos=2)
    [first] = db.jobs_of(JobType.RESEARCH_FAST)
    [payload] = fast_payloads(db)
    db.finish_job(
        first.id,
        FastResult(
            case_id=payload.case_id,
            status="needs_user_input",
            question_en="Which letter first?",
        ),
    )
    await settle()

    await pipe.handle(inbound("La de USCIS"))

    old, new = fast_payloads(db)
    assert (new.case_id, new.document_ids) == (old.case_id, old.document_ids)
    assert new.user_note_en is not None and "La de USCIS" in new.user_note_en
    assert old.user_note_en is None
    assert db.outbound_templates()[-1] == "letter.reading_again"


async def test_text_without_an_open_research_question_is_a_normal_turn(
    pipe: InboundPipe, db: FakeDB
) -> None:
    await use_spanish(db)
    await send_letter(pipe)

    await pipe.handle(inbound("hola"))

    assert len(db.jobs_of(JobType.RESEARCH_FAST)) == 1
    assert "letter.reading_again" not in db.outbound_templates()
