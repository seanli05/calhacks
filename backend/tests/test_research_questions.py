"""C38: the user's factual questions go to research; the answer comes back on its own."""

import asyncio
import json
from typing import Any

import pytest
from app.contracts import JobType, QuestionAnswer, ResearchQuestionJob
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.research_questions import ResearchQuestions
from app.orchestrator.tools import CaseTools
from app.relay.templates import render
from whatsapp_fakes import FakeDB, FakeTranslator, FakeWhatsApp, use_spanish

SOURCE = "https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum"


@pytest.fixture
def questions(
    whatsapp: FakeWhatsApp, translator: FakeTranslator, job_watcher: JobWatcher
) -> ResearchQuestions:
    fake: Any = translator
    return ResearchQuestions(whatsapp, fake, job_watcher)


async def settle() -> None:
    await asyncio.sleep(0.1)


async def ask(db: FakeDB, questions: ResearchQuestions, whatsapp: FakeWhatsApp) -> str:
    user = await use_spanish(db)
    tools = CaseTools(user, whatsapp, research_questions=questions)
    result = json.loads(await tools.ask_official_source("What do I bring?", None))
    assert result["queued"] is True
    [job] = db.jobs_of(JobType.RESEARCH_QUESTION)
    return job.id


async def test_tool_queues_the_question_in_english(
    db: FakeDB, questions: ResearchQuestions, whatsapp: FakeWhatsApp
) -> None:
    job_id = await ask(db, questions, whatsapp)
    payload = ResearchQuestionJob.model_validate(db.jobs[job_id].payload)
    assert payload.question_en == "What do I bring?"
    assert payload.case_id is None
    assert db.messages == []  # the turn tells the user it's looking


async def test_tool_refuses_someone_elses_case(
    db: FakeDB, questions: ResearchQuestions, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    tools = CaseTools(user, whatsapp, research_questions=questions)
    result = json.loads(await tools.ask_official_source("What?", "case_other"))
    assert "error" in result
    assert db.jobs_of(JobType.RESEARCH_QUESTION) == []


async def test_answer_goes_out_translated_with_its_sources(
    db: FakeDB, questions: ResearchQuestions, whatsapp: FakeWhatsApp
) -> None:
    job_id = await ask(db, questions, whatsapp)
    db.finish_job(
        job_id,
        QuestionAnswer(
            status="answered",
            answer_en="Bring your ID.",
            sources=[{"url": SOURCE, "quote": "Bring ID"}],
        ),
    )
    await settle()

    [message] = db.messages
    assert message.body_original == f"[es] Bring your ID.\n\n- {SOURCE}"
    assert message.body_en == f"Bring your ID.\n\n- {SOURCE}"


@pytest.mark.parametrize(
    ("status", "template"),
    [
        ("declined_legal_advice", "research_question.legal_advice"),
        ("declined_asylum_claim", "research_question.asylum_claim"),
        ("not_confirmed", "research_question.not_found"),
        ("out_of_scope", "research_question.not_found"),
    ],
)
async def test_declines_use_fixed_templates(
    db: FakeDB,
    questions: ResearchQuestions,
    whatsapp: FakeWhatsApp,
    status: str,
    template: str,
) -> None:
    """C33, C34: "no legal advice" never depends on a model or a translation."""
    job_id = await ask(db, questions, whatsapp)
    db.finish_job(job_id, QuestionAnswer(status=status, reason_en="Legal advice."))
    await settle()

    assert db.outbound_templates() == [template]
    assert whatsapp.sent == [render(template, "es")]


async def test_failed_job_says_try_again(
    db: FakeDB, questions: ResearchQuestions, whatsapp: FakeWhatsApp
) -> None:
    job_id = await ask(db, questions, whatsapp)
    db.fail_job(job_id, "timeout")
    await settle()

    assert db.outbound_templates() == ["research_question.failed"]


async def test_untranslated_answer_still_gives_the_sources(
    db: FakeDB, whatsapp: FakeWhatsApp, job_watcher: JobWatcher
) -> None:
    fake: Any = FakeTranslator(fail=True)
    questions = ResearchQuestions(whatsapp, fake, job_watcher)
    job_id = await ask(db, questions, whatsapp)
    db.finish_job(
        job_id,
        QuestionAnswer(
            status="answered",
            answer_en="Bring your ID.",
            sources=[{"url": SOURCE, "quote": "Bring ID"}],
        ),
    )
    await settle()

    assert db.outbound_templates() == ["research_question.untranslated"]
    assert SOURCE in whatsapp.sent[0]
