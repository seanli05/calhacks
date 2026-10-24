"""The user's factual questions, answered by research from official sources (C38).

The Claude turn queues a `research_question` job through a tool and tells the user
it's looking; the answer comes back here and goes out on its own. An answer is
translated free text with its official sources (the orchestrator may write free
text, rule 1). A decline gets a fixed template, so "no legal advice" and "we don't
discuss the claim" never depend on a model or a translation (C33, C34).
"""

import logging

from pydantic import ValidationError

from app.contracts import (
    Component,
    JobStatus,
    QuestionAnswer,
    ResearchQuestionJob,
    ResearchQuestionStatus,
)
from app.contracts.common import CaseId
from app.db import jobs, reads, tables
from app.orchestrator.job_watch import JobWatcher
from app.relay.outbound import send_template, send_text
from app.relay.whatsapp import WhatsApp, WhatsAppSendError
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

MAX_SOURCES = 3

_DECLINE_TEMPLATES = {
    ResearchQuestionStatus.NOT_CONFIRMED: "research_question.not_found",
    ResearchQuestionStatus.OUT_OF_SCOPE: "research_question.not_found",
    ResearchQuestionStatus.DECLINED_LEGAL_ADVICE: "research_question.legal_advice",
    ResearchQuestionStatus.DECLINED_ASYLUM_CLAIM: "research_question.asylum_claim",
}


class ResearchQuestions:
    def __init__(
        self, whatsapp: WhatsApp, translator: Translator | None, watcher: JobWatcher
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._watcher = watcher

    async def ask(
        self, user: tables.User, question_en: str, case_id: CaseId | None
    ) -> str:
        """Queue the question; returns the job ID. The answer is sent when it's done."""
        job = await jobs.enqueue(
            ResearchQuestionJob(
                user_id=user.id, case_id=case_id, question_en=question_en
            ),
            Component.ORCHESTRATOR,
            user.id,
            case_id,
        )
        logger.info(
            "Research question queued user_id=%s case_id=%s job_id=%s",
            user.id,
            case_id,
            job.id,
        )
        self._watcher.watch(job.id, self.finished)
        return job.id

    async def finished(self, job: tables.Job) -> None:
        user = await reads.get_user(job.user_id)
        if user is None:
            return
        try:
            await self._send(user, job)
        except WhatsAppSendError as exc:
            logger.error("Research answer not sent job_id=%s: %s", job.id, exc)

    async def _send(self, user: tables.User, job: tables.Job) -> None:
        if job.status == JobStatus.FAILED:
            logger.error("Research question failed job_id=%s: %s", job.id, job.error)
            await send_template(
                self._whatsapp, user, "research_question.failed", case_id=job.case_id
            )
            return
        try:
            answer = QuestionAnswer.model_validate(job.result)
        except ValidationError:
            logger.exception("Bad research answer job_id=%s", job.id)
            await send_template(
                self._whatsapp, user, "research_question.failed", case_id=job.case_id
            )
            return
        if answer.status != ResearchQuestionStatus.ANSWERED or not answer.answer_en:
            await send_template(
                self._whatsapp,
                user,
                _DECLINE_TEMPLATES[ResearchQuestionStatus(answer.status)],
                case_id=job.case_id,
            )
            return
        urls = list(dict.fromkeys(source.url for source in answer.sources))
        sources = "\n".join(f"- {url}" for url in urls[:MAX_SOURCES])
        text = await localize(self._translator, answer.answer_en, user.language or "en")
        if text is None:
            await send_template(
                self._whatsapp,
                user,
                "research_question.untranslated",
                {"sources": sources},
                case_id=job.case_id,
            )
            return
        await send_text(
            self._whatsapp,
            user,
            f"{text}\n\n{sources}",
            body_en=f"{answer.answer_en}\n\n{sources}",
            case_id=job.case_id,
        )
        logger.info("Research answer sent job_id=%s", job.id)
