"""Goal 6 on fakes: R1 → explanation, R2 → verdict and consent, the consent gate
(rule 4, C21), and the post-call summary. No Anthropic, no Twilio, no database."""

import asyncio
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import pytest
from app.contracts import (
    CallOutcome,
    CallReport,
    Component,
    DeepResult,
    Event,
    EventType,
    FastResult,
    JobStatus,
    JobType,
    ResearchDeepJob,
    ResearchFastJob,
    VerificationStatus,
)
from app.db import tables
from app.db.ids import new_id
from app.db.tables import utcnow
from app.orchestrator.call_status import CallStatusWatcher
from app.orchestrator.consent import GOAL_CONTEXT, ConsentGate
from app.orchestrator.conversation import Conversation
from app.orchestrator.dates import format_date, format_time
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letter_result import LetterResults, date_line
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.tools import CaseTools
from app.orchestrator.verdicts import Verdicts
from app.relay.ask_user import AskUser
from app.relay.outbound import send_text
from app.relay.templates import LANGUAGES, render
from whatsapp_fakes import (
    NUMBER,
    FakeDB,
    FakeTranslator,
    FakeWhatsApp,
    inbound,
    use_spanish,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def fixture(name: str, **overrides: Any) -> dict[str, Any]:
    return {**json.loads((FIXTURES / name).read_text(encoding="utf-8")), **overrides}


async def until(condition: Any, timeout_s: float = 3.0) -> None:
    """Wait on a deadline, not a count: on Windows a busy loop runs sub-15 ms sleeps
    at once, so counted waits end early."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.01)


async def finished_fast_job(
    db: FakeDB, user: tables.User, case_id: str, result: FastResult
) -> tables.Job:
    job = await db.enqueue(
        ResearchFastJob(
            case_id=case_id, user_id=user.id, document_ids=["doc_1"], user_language="es"
        ),
        Component.ORCHESTRATOR,
        user.id,
        case_id,
    )
    db.finish_job(job.id, result)
    return (await db.get_job(job.id)) or job


async def deep_done(
    db: FakeDB, user: tables.User, case_id: str, result: DeepResult
) -> None:
    """Research finishing its deep pass: the job's R2, then `research.deep_done`."""
    job = await db.enqueue(
        ResearchDeepJob(case_id=case_id, user_id=user.id, document_ids=["doc_1"]),
        Component.RESEARCH_AGENT,
        user.id,
        case_id,
    )
    db.finish_job(job.id, result)
    await db.append_event(
        Event(
            event_id=new_id("event"),
            created_at=utcnow(),
            type=EventType.RESEARCH_DEEP_DONE,
            source=Component.RESEARCH_AGENT,
            user_id=user.id,
            case_id=case_id,
            job_id=job.id,
            summary_en="Finished checking the letter",
        )
    )


def deep_result(case_id: str, status: VerificationStatus, **changes: Any) -> DeepResult:
    deep = DeepResult.model_validate(fixture("deep_result.json", case_id=case_id))
    verification = deep.verification.model_copy(
        update={"status": status, **changes.pop("verification", {})}
    )
    return deep.model_copy(update={"verification": verification, **changes})


# Dates (5.4)


def test_dates_are_written_the_way_the_user_reads_them() -> None:
    interview = dt.date(2026, 11, 18)
    assert format_date(interview, "es") == "miércoles 18 de noviembre de 2026"
    assert format_date(interview, "en") == "Wednesday, November 18, 2026"
    assert format_date(interview, "fa") == "چهارشنبه ۱۸ نومبر ۲۰۲۶"
    assert format_date(interview, "ht") == "2026-11-18"  # no wrong month names
    assert format_time("08:30", "es") == "8:30 a. m."
    assert format_time("13:05", "en") == "1:05 PM"
    assert format_time("00:15", "en") == "12:15 AM"


@pytest.mark.parametrize(
    ("hh_mm", "expected"),
    [
        ("08:30", "۸:۳۰ صبح"),
        ("11:59", "۱۱:۵۹ صبح"),
        ("12:00", "۱۲:۰۰ بعد از ظهر"),
        ("16:30", "۴:۳۰ بعد از ظهر"),
        ("20:00", "۸:۰۰ شب"),
    ],
)
def test_dari_times_read_morning_afternoon_and_night(hh_mm: str, expected: str) -> None:
    assert format_time(hh_mm, "fa") == expected


def test_no_supported_language_gets_an_iso_date() -> None:
    """An ISO date inside Dari (or any template language) would read as noise."""
    for language in LANGUAGES:
        assert "-" not in format_date(dt.date(2026, 1, 5), language), language


# R1 (6.1)


async def test_explanation_carries_the_date_checklist_and_closing(
    db: FakeDB,
    whatsapp: FakeWhatsApp,
    letter_results: LetterResults,
    verdicts: Verdicts,
) -> None:
    user = await use_spanish(db)
    result = FastResult.model_validate(fixture("fast_result.json", case_id="case_1"))

    await letter_results.fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    assert message.sender == "orchestrator"
    assert message.case_id == "case_1"
    # Only the summary paragraph; the details repeat the date line and checklist (C41).
    summary, details = result.explanation_en.split("\n\n")
    assert message.body_original.startswith(f"[es] {summary}\n\n")
    assert details not in message.body_original
    # The date line is a template with the date formatted in code, never translated.
    assert (
        render(
            "letter.appointment",
            "es",
            date="miércoles 18 de noviembre de 2026",
            time="8:30 a. m.",
        )
        in message.body_original
    )
    assert "[es] Who must come:\n- All dependents" in message.body_original
    assert message.body_original.endswith(render("letter.checking", "es"))
    assert message.body_en is not None
    assert "Wednesday, November 18, 2026, at 8:30 AM" in message.body_en
    assert "What to bring:" in message.body_en
    assert "<ref:" not in message.body_original
    assert verdicts.is_watching("case_1")


async def test_explanation_without_a_summary_paragraph_is_sent_whole(
    db: FakeDB, letter_results: LetterResults
) -> None:
    user = await use_spanish(db)
    one_paragraph = "This is a notice from USCIS. Your interview is on November 18."
    result = FastResult.model_validate(
        fixture("fast_result.json", case_id="case_1", explanation_en=one_paragraph)
    )

    await letter_results.fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    assert message.body_original.startswith(f"[es] {one_paragraph}\n\n")


async def test_untranslated_explanation_falls_back_to_templates_never_english(
    db: FakeDB, whatsapp: FakeWhatsApp, verdicts: Verdicts, conversation: Conversation
) -> None:
    user = await use_spanish(db)
    result = FastResult.model_validate(fixture("fast_result.json", case_id="case_1"))
    failing: Any = FakeTranslator(fail=True)

    await LetterResults(
        whatsapp, failing, verdicts, conversation=conversation
    ).fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    assert message.body_original.startswith(render("letter.explain_failed", "es"))
    assert "18 de noviembre" in message.body_original
    assert "This is a notice" not in message.body_original


async def test_dari_explanation_dates_the_interview_in_dari(
    db: FakeDB, letter_results: LetterResults
) -> None:
    user = await db.get_or_create_user(NUMBER)
    user.language = "fa"
    result = FastResult.model_validate(fixture("fast_result.json", case_id="case_1"))

    await letter_results.fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    body = message.body_original
    summary = (result.explanation_en or "").split("\n\n")[0]
    assert body.startswith(f"[fa] {summary}\n\n")
    assert "مصاحبهٔ شما: چهارشنبه ۱۸ نومبر ۲۰۲۶، ساعت ۸:۳۰ صبح" in body
    assert "2026-11-18" not in body and "8:30" not in body
    assert body.endswith(render("letter.checking", "fa"))
    assert "Wednesday, November 18, 2026, at 8:30 AM" in (message.body_en or "")


async def test_unreadable_photo_asks_for_a_retake_with_the_tip(
    db: FakeDB, letter_results: LetterResults, verdicts: Verdicts
) -> None:
    user = await use_spanish(db)
    result = FastResult(
        case_id="case_1", status="needs_better_image", image_issue="It's blurry."
    )

    await letter_results.fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    assert message.template == "letter.retake_tip"
    assert "[es] It's blurry." in message.body_original
    assert message.body_en == render("letter.retake_tip", "en", tip="It's blurry.")
    assert not verdicts.is_watching("case_1")  # no deep pass for an unreadable photo


def test_date_only_appointment_leaves_the_time_out() -> None:
    data = fixture("fast_result.json")
    data["appointment"] = {"date": "2026-11-18", "citation": "p1"}
    line = date_line(FastResult.model_validate(data), "en")
    assert line == render(
        "letter.appointment_date", "en", date=format_date(dt.date(2026, 11, 18), "en")
    )


async def test_needs_user_input_asks_research_question_and_waits(
    db: FakeDB, letter_results: LetterResults, verdicts: Verdicts
) -> None:
    """C39: the user hears the question in their language; no explanation, and no
    verdict is watched until research has read the letter."""
    user = await use_spanish(db)
    result = FastResult(
        case_id="case_1", status="needs_user_input", question_en="Which letter first?"
    )

    await letter_results.fast_done(await finished_fast_job(db, user, "case_1", result))

    [message] = db.messages
    assert message.body_original == "[es] Which letter first?"
    assert message.body_en == "Which letter first?"
    question = letter_results.question(user.id)
    assert question is not None and question.case_id == "case_1"
    assert question.document_ids == ["doc_1"]
    assert not verdicts.is_watching("case_1")


async def test_research_question_survives_a_payload_that_no_longer_validates(
    db: FakeDB, letter_results: LetterResults
) -> None:
    user = await use_spanish(db)
    result = FastResult(
        case_id="case_1", status="needs_user_input", question_en="Which letter first?"
    )
    job = await finished_fast_job(db, user, "case_1", result)
    job.payload = {"job": "research_fast", "document_ids": ["doc_1"]}

    await letter_results.fast_done(job)

    assert db.messages[-1].body_en == "Which letter first?"
    question = letter_results.question(user.id)
    assert question is not None and question.document_ids == []


# R2 (6.2)


async def test_verified_letter_gets_the_verdict_and_consent_request_in_one_message(
    db: FakeDB, verdicts: Verdicts, consent: ConsentGate, translator: FakeTranslator
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    verdicts.watch(user.id, case.id, since=utcnow())

    await deep_done(
        db, user, case.id, deep_result(case.id, VerificationStatus.VERIFIED)
    )
    await until(lambda: consent.pending(user.id) is not None)

    assert db.outbound_templates() == ["verification.verified_call"]
    asked = db.messages[-1]
    assert asked.body_original.startswith(render("verification.verified", "es"))
    assert "[es] Confirm the interview is still scheduled" in asked.body_original
    assert asked.body_en is not None and "Confirm the interview" in asked.body_en
    # Rule 4: the goal reads as what the call is for, not as a request to the user.
    assert translator.contexts[-1] == GOAL_CONTEXT
    [requested] = [e for e in db.events if e.type == EventType.CONSENT_REQUESTED]
    assert requested.data == {"agency": "USCIS"}


async def test_consent_request_waits_while_another_question_is_open(
    db: FakeDB, pipe: InboundPipe, verdicts: Verdicts, consent: ConsentGate
) -> None:
    """One numbered question at a time: a "1" must answer exactly one."""
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    letter = await db.create_document(user.id, ["media_old"])
    case.document_ids = [letter.id]
    await pipe.handle(inbound(photos=1))  # "same letter or new?"

    refusal = await consent.request(user, case.id)  # the turn's tool
    assert refusal is not None and "Another numbered question" in refusal

    await verdicts.react(user, deep_result(case.id, VerificationStatus.VERIFIED))
    assert db.outbound_templates() == ["letter.same_or_new", "verification.verified"]
    assert consent.pending(user.id) is None

    await pipe.handle(inbound("1"))  # answers the photo question, not the call

    assert db.outbound_templates()[-2:] == ["letter.pages_added", "consent.request"]
    assert consent.pending(user.id) is not None
    assert db.jobs_of(JobType.CALL) == []


async def test_explanation_waits_for_a_turn_in_progress(
    db: FakeDB,
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Letters,
    letter_results: LetterResults,
    conversation: Conversation,
) -> None:
    """A turn's reply and the explanation never cross: whichever starts second is
    written after the first has gone out."""
    user = await use_spanish(db)
    release = asyncio.Event()

    async def turn(user: tables.User, message_id: str, **_: bool) -> None:
        await release.wait()
        await send_text(whatsapp, user, "turn reply")

    async def detect(text: str) -> None:
        return None

    pipe = InboundPipe(
        whatsapp, detect, ask_user, letters, turn=turn, conversation=conversation
    )
    handling = asyncio.create_task(pipe.handle(inbound("ya está")))
    await until(lambda: conversation.speaking(user.id).locked())
    result = FastResult.model_validate(fixture("fast_result.json", case_id="case_1"))
    job = await finished_fast_job(db, user, "case_1", result)
    explaining = asyncio.create_task(letter_results.fast_done(job))
    await asyncio.sleep(0.05)
    assert [m.direction for m in db.messages] == ["in"]

    # The user sees "typing…" on their message while the turn waits and works.
    assert set(whatsapp.typing_sids) == {db.messages[0].twilio_sid}

    release.set()
    await asyncio.gather(handling, explaining)

    assert not conversation.is_typing(user.id)
    first, second = [m.body_original for m in db.messages if m.direction == "out"]
    assert first == "turn reply"
    assert second.startswith("[es] This is a USCIS notice")


@pytest.mark.parametrize(
    ("status", "template"),
    [
        (VerificationStatus.SUSPICIOUS, "verification.suspicious"),
        (VerificationStatus.UNKNOWN, "verification.unknown"),
    ],
)
async def test_suspicious_or_unknown_letter_never_offers_a_call(
    db: FakeDB,
    verdicts: Verdicts,
    consent: ConsentGate,
    status: VerificationStatus,
    template: str,
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user, status=status)
    deep = deep_result(
        case.id, status, verification={"red_flags": ["Asks for a fee by phone"]}
    )

    await verdicts.react(user, deep)

    assert db.outbound_templates() == [template]
    assert consent.pending(user.id) is None
    if status == VerificationStatus.SUSPICIOUS:
        assert "[es] - Asks for a fee by phone" in db.messages[-1].body_original


# The consent gate (6.3)


async def asked(db: FakeDB, consent: ConsentGate) -> tuple[tables.User, tables.Case]:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    assert await consent.request(user, case.id) is None
    return user, case


async def test_yes_queues_exactly_one_call_from_the_users_reply(
    db: FakeDB,
    pipe: InboundPipe,
    consent: ConsentGate,
    call_status: CallStatusWatcher,
    job_watcher: JobWatcher,
) -> None:
    user, case = await asked(db, consent)

    await pipe.handle(inbound("1"))

    [job] = db.jobs_of(JobType.CALL)
    yes = next(m for m in db.messages if m.body_original == "1")
    assert job.payload["consent_message_id"] == yes.id
    assert job.payload["case_id"] == case.id
    assert job.payload["brief_id"] == db.briefs[case.id].id
    assert job.payload["dial_number_source"] == "official_phone"
    assert "+15105550199" not in json.dumps(job.payload)  # no numbers in jobs (C6)
    given = next(e for e in db.events if e.type == EventType.CONSENT_GIVEN)
    assert given.data == {"consent_message_id": yes.id}
    assert call_status.is_watching(user.id)
    assert job_watcher.is_watching(job.id)
    assert db.outbound_templates()[-1] == "consent.given"

    # One YES is one call (C21): another "1" isn't a second consent.
    await pipe.handle(inbound("1"))
    assert len(db.jobs_of(JobType.CALL)) == 1


async def test_yes_in_words_counts_and_no_declines(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate
) -> None:
    await asked(db, consent)
    await pipe.handle(inbound("Sí."))
    assert len(db.jobs_of(JobType.CALL)) == 1

    user = await use_spanish(db)
    second = db.add_verified_case(user)
    assert await consent.request(user, second.id) is None
    await pipe.handle(inbound("2"))

    assert len(db.jobs_of(JobType.CALL)) == 1
    assert db.outbound_templates()[-1] == "consent.declined"
    assert db.event_types()[-1] == EventType.CONSENT_DECLINED


async def test_other_text_is_reprompted_without_a_turn(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate
) -> None:
    user, _ = await asked(db, consent)

    await pipe.handle(inbound("¿cuánto tarda?"))

    assert db.outbound_templates()[-1] == "consent.reprompt"
    assert consent.pending(user.id) is not None
    assert db.jobs_of(JobType.CALL) == []


async def test_yes_after_the_verdict_changed_is_refused(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate
) -> None:
    """The gate checks again at the YES: research may have changed its verdict."""
    _, case = await asked(db, consent)
    db.verifications[case.id].status = VerificationStatus.SUSPICIOUS

    await pipe.handle(inbound("1"))

    assert db.jobs_of(JobType.CALL) == []
    assert db.outbound_templates()[-1] == "consent.unavailable"
    assert EventType.CONSENT_GIVEN not in db.event_types()


@pytest.mark.parametrize(
    ("status", "phone"),
    [
        (VerificationStatus.UNKNOWN, "+15105550199"),
        (VerificationStatus.SUSPICIOUS, "+15105550199"),
        (VerificationStatus.VERIFIED, None),  # rule 2: no verified number to dial
    ],
)
async def test_no_consent_request_without_a_verified_number(
    db: FakeDB, consent: ConsentGate, status: VerificationStatus, phone: str | None
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user, status=status, official_phone=phone)

    assert await consent.request(user, case.id) is not None
    assert db.messages == []
    assert consent.pending(user.id) is None


async def test_no_second_request_while_a_call_is_running(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate
) -> None:
    user, case = await asked(db, consent)
    await pipe.handle(inbound("1"))

    refusal = await consent.request(user, case.id)

    assert refusal is not None and "in progress" in refusal


async def test_request_consent_tool_only_opens_the_question(
    db: FakeDB, whatsapp: FakeWhatsApp, consent: ConsentGate
) -> None:
    """The turn asks in its own words (the reply); the tool sends nothing."""
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    tools = CaseTools(user, whatsapp, consent)

    result = json.loads(await tools.request_consent(case.id))

    assert result["opened"] == case.id
    assert "Confirm the interview" in result["note"]
    assert tools.consent_question == case.id
    assert db.messages == []
    assert consent.pending(user.id) is not None
    [requested] = [e for e in db.events if e.type == EventType.CONSENT_REQUESTED]
    assert requested.data == {"agency": "USCIS", "via": "words"}
    assert db.jobs_of(JobType.CALL) == []


async def test_consent_request_survives_rows_that_no_longer_validate(
    db: FakeDB, consent: ConsentGate
) -> None:
    """A brief or R1 written before a contract change: the generic request, to
    USCIS, and the YES still works."""
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    case.fast_result = {"status": "ok", "issuer": "Asylum Office"}
    db.briefs[case.id].brief = {"call_goal_en": "Confirm the interview is still on"}

    assert await consent.request(user, case.id) is None

    assert db.outbound_templates() == ["consent.request_generic"]
    [requested] = [e for e in db.events if e.type == EventType.CONSENT_REQUESTED]
    assert requested.data == {"agency": "USCIS"}
    assert consent.pending(user.id) is not None


# The post-call summary (6.4)


async def call_ends(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate, report: CallReport | None
) -> tables.User:
    user, case = await asked(db, consent)
    await pipe.handle(inbound("1"))
    [job] = db.jobs_of(JobType.CALL)
    if report is None:
        db.fail_job(job.id, "phone agent crashed")
    else:
        db.finish_job(job.id, report.model_copy(update={"case_id": case.id}))
    return user


def report(**changes: Any) -> CallReport:
    return CallReport.model_validate(fixture("call_report.json", **changes))


async def test_resolved_call_gets_the_summary_and_a_close_suggestion(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate
) -> None:
    user = await call_ends(db, pipe, consent, report(followup_needed=False))
    close = render("summary.suggest_close", "es")
    await until(lambda: db.messages[-1].body_original.endswith(close))

    # One message: the summary, ending with the close suggestion (pacing).
    summary = db.messages[-1]
    assert db.messages[-2].direction == "out"
    assert db.messages[-2].template == "consent.given"
    assert summary.sender == "orchestrator"
    assert summary.user_id == user.id
    assert summary.body_en is not None
    assert summary.body_en.endswith(render("summary.suggest_close", "en"))
    assert summary.body_original.startswith(
        "[es] Here's how the call with USCIS went:\n- Interview is still on"
    )
    assert render("summary.reference", "es", reference="R-55821") in (
        summary.body_original
    )
    assert "martes 17 de noviembre de 2026" in summary.body_original
    assert summary.body_en is not None and "Tuesday, November 17, 2026" in (
        summary.body_en
    )


async def test_resolved_call_with_follow_up_doesnt_suggest_closing(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate, job_watcher: JobWatcher
) -> None:
    await call_ends(db, pipe, consent, report(followup_needed=True))
    [job] = db.jobs_of(JobType.CALL)
    await until(lambda: not job_watcher.is_watching(job.id))

    assert db.messages[-1].sender == "orchestrator"
    close = render("summary.suggest_close", "es")
    assert not db.messages[-1].body_original.endswith(close)


async def test_a_call_the_user_ended_is_confirmed_without_a_retry_offer(
    db: FakeDB, pipe: InboundPipe, consent: ConsentGate, job_watcher: JobWatcher
) -> None:
    user = await call_ends(db, pipe, consent, report(outcome=CallOutcome.CANCELLED))
    [job] = db.jobs_of(JobType.CALL)
    await until(lambda: not job_watcher.is_watching(job.id))

    assert db.outbound_templates()[-1] == "summary.cancelled"
    assert consent.pending(user.id) is None


@pytest.mark.parametrize(
    ("call_report", "template"),
    [
        (None, "summary.call_failed_retry"),
        (report(outcome=CallOutcome.FAILED), "summary.call_failed_retry"),
        # The status watcher already said we couldn't reach them.
        (report(outcome=CallOutcome.USER_UNREACHABLE), "consent.request"),
    ],
    ids=["job-failed", "hold-exceeded", "unreachable"],
)
async def test_unfinished_call_offers_a_retry_with_new_consent(
    db: FakeDB,
    pipe: InboundPipe,
    consent: ConsentGate,
    call_report: CallReport | None,
    template: str,
) -> None:
    """C21: a retry asks again, and the user is told why, in one message."""
    user = await call_ends(db, pipe, consent, call_report)
    await until(lambda: db.outbound_templates()[-1] == template)

    assert db.outbound_templates()[-2] == "consent.given"
    assert consent.pending(user.id) is not None
    assert len(db.jobs_of(JobType.CALL)) == 1  # nothing queued without a new YES
    assert db.jobs_of(JobType.CALL)[0].status == (
        JobStatus.FAILED if call_report is None else JobStatus.DONE
    )
