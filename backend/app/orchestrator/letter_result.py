"""Turning R1 into the user's explanation (Plan.md → R1, C9, C31, C46; Goal 6.1).

C46: the letter is checked before it's explained. If research's instant checks
already found signs of a scam (R1 `verification` is suspicious), the user gets a warm
warning at once and never the explanation. Otherwise "I'm just double-checking it's
really from USCIS", and the explanation waits for the verdict (verdicts.py), which
sends both in one message.

The explanation: the summary paragraph (C41), the interview date and time, and the
checklist (who must come, what to bring, other deadlines). The explanation and
checklist are translated free text (in parallel); the date line is a relay template,
with the date formatted in code, so the one fact that must survive is never left to a
model. If translation fails, the user gets the templates and an offer to explain,
never English. Messages are sent while holding the user's conversation lock, so they
never cross a turn's reply (conversation.py).
"""

import asyncio
import logging
from dataclasses import dataclass
from functools import partial

from pydantic import ValidationError

from app.contracts import (
    ChecklistKind,
    FastResult,
    FastResultStatus,
    ResearchFastJob,
    VerificationStatus,
)
from app.contracts.common import CaseId, DocumentId, LanguageCode, UserId
from app.db import jobs, reads, tables
from app.orchestrator.conversation import Conversation
from app.orchestrator.dates import format_date, format_time
from app.orchestrator.verdicts import Verdicts
from app.relay.outbound import send_template, send_text
from app.relay.templates import render
from app.relay.whatsapp import WhatsApp, WhatsAppSendError
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

_HEADINGS = {
    ChecklistKind.WHO_MUST_COME: "Who must come:",
    ChecklistKind.BRING: "What to bring:",
    ChecklistKind.DEADLINE: "Other deadlines:",
}


def checklist_en(result: FastResult) -> str:
    """The checklist grouped by kind, in English, or "" if there's none."""
    sections = []
    for kind, heading in _HEADINGS.items():
        items = [f"- {c.item}" for c in result.checklist_en if c.kind == kind]
        if items:
            sections.append("\n".join([heading, *items]))
    return "\n\n".join(sections)


def date_line(result: FastResult, language: LanguageCode) -> str | None:
    """The interview date and time, or else the deadline, rendered in `language`."""
    if result.appointment is not None and result.appointment.time is None:
        return render(
            "letter.appointment_date",
            language,
            date=format_date(result.appointment.date, language),
        )
    if result.appointment is not None:
        return render(
            "letter.appointment",
            language,
            date=format_date(result.appointment.date, language),
            time=format_time(result.appointment.time, language),
        )
    if result.deadline is not None:
        return render(
            "letter.deadline", language, date=format_date(result.deadline, language)
        )
    return None


@dataclass(frozen=True)
class LetterQuestion:
    """Research asked the user something before it can read the letter (C39)."""

    case_id: CaseId
    document_ids: list[DocumentId]


class LetterResults:
    def __init__(
        self,
        whatsapp: WhatsApp,
        translator: Translator | None,
        verdicts: Verdicts,
        *,
        conversation: Conversation,
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._verdicts = verdicts
        self._conversation = conversation
        # One open question per user; in memory, like the photo batcher.
        self._questions: dict[UserId, LetterQuestion] = {}

    def question(self, user_id: UserId) -> LetterQuestion | None:
        return self._questions.get(user_id)

    def take_question(self, user_id: UserId) -> LetterQuestion | None:
        return self._questions.pop(user_id, None)

    def verdict_pending(self, user_id: UserId) -> bool:
        return self._verdicts.watching_for(user_id)

    async def fast_done(self, job: tables.Job) -> None:
        """React to a finished fast pass (the latest one for its case)."""
        try:
            result = FastResult.model_validate(job.result)
        except ValidationError:
            logger.exception("Bad R1 case_id=%s job_id=%s", job.case_id, job.id)
            return
        user = await reads.get_user(job.user_id)
        if user is None:
            return
        async with self._conversation.speaking(user.id):
            await self._react(user, result, job)

    async def _react(
        self, user: tables.User, result: FastResult, job: tables.Job
    ) -> None:
        if result.status == FastResultStatus.NEEDS_USER_INPUT:
            await self._ask(user, result, job)
            return
        readable = result.status != FastResultStatus.NEEDS_BETTER_IMAGE
        scam = readable and result.verification == VerificationStatus.SUSPICIOUS
        try:
            if not readable:
                await self._retake(user, result)
            elif scam:
                # C46: never explained; the deep pass's verdict isn't sent either.
                await send_template(
                    self._whatsapp,
                    user,
                    "letter.looks_like_scam",
                    case_id=result.case_id,
                )
                logger.info(
                    "Scam warning sent before explaining case_id=%s", result.case_id
                )
            else:
                await send_template(
                    self._whatsapp,
                    user,
                    "letter.double_checking",
                    case_id=result.case_id,
                )
        except WhatsAppSendError as exc:
            logger.error(
                "Letter result not sent case_id=%s job_id=%s: %s",
                result.case_id,
                job.id,
                exc,
            )
        if readable and not scam:
            self._verdicts.watch(
                user.id,
                result.case_id,
                since=job.created_at,
                explain=partial(self.explanation, result),
            )

    async def explanation(
        self, result: FastResult, user: tables.User
    ) -> tuple[str, str]:
        """The letter's explanation in the user's language, and its English. The
        verdict closes the message (verdicts.py)."""
        language = user.language or "en"
        explanation_en = _summary(result.explanation_en or "")
        checklist = checklist_en(result)
        explanation, translated_checklist = await asyncio.gather(
            self._localize(explanation_en, language),
            self._localize(checklist, language),
        )
        if explanation is None or translated_checklist is None:
            logger.warning("Explanation not translated case_id=%s", result.case_id)
            return (
                _join(
                    render("letter.explain_failed", language),
                    date_line(result, language),
                ),
                _join(render("letter.explain_failed", "en"), date_line(result, "en")),
            )
        return (
            _join(explanation, date_line(result, language), translated_checklist),
            _join(explanation_en, date_line(result, "en"), checklist),
        )

    async def _retake(self, user: tables.User, result: FastResult) -> None:
        """Plan.md → Failure rules: unreadable photo; ask again with research's tip."""
        tip_en = result.image_issue
        tip = await self._localize(tip_en, user.language or "en") if tip_en else None
        if tip_en and tip:
            await send_template(
                self._whatsapp,
                user,
                "letter.retake_tip",
                {"tip": tip},
                values_en={"tip": tip_en},
            )
        else:
            await send_template(self._whatsapp, user, "letter.retake")

    async def _ask(
        self, user: tables.User, result: FastResult, job: tables.Job
    ) -> None:
        """C39: ask research's question; the reply re-runs the fast pass (Letters).
        The verdict isn't watched yet: research hasn't read the letter."""
        question_en = result.question_en or ""
        question = await self._localize(question_en, user.language or "en")
        document_ids = _document_ids(job)
        self._questions[user.id] = LetterQuestion(result.case_id, document_ids)
        try:
            if question:
                await send_text(
                    self._whatsapp,
                    user,
                    question,
                    body_en=question_en,
                    case_id=result.case_id,
                )
            else:
                # Untranslated: today the only question is "which letter first?".
                await send_template(
                    self._whatsapp, user, "letter.which_letter", case_id=result.case_id
                )
        except WhatsAppSendError as exc:
            logger.error(
                "Letter question not sent case_id=%s job_id=%s: %s",
                result.case_id,
                job.id,
                exc,
            )
        logger.info("Asked the user research's question case_id=%s", result.case_id)

    async def _localize(self, text_en: str, language: LanguageCode) -> str | None:
        if not text_en:
            return ""
        return await localize(self._translator, text_en, language)


def _document_ids(job: tables.Job) -> list[DocumentId]:
    """The fast job's documents, or none if its stored payload no longer validates
    (the user's answer then re-runs the pass without them)."""
    try:
        payload = jobs.payload_of(job)
    except ValidationError:
        logger.exception(
            "Bad fast job payload case_id=%s job_id=%s", job.case_id, job.id
        )
        return []
    if not isinstance(payload, ResearchFastJob):
        logger.error(
            "Not a fast job case_id=%s job_id=%s: %s", job.case_id, job.id, payload.job
        )
        return []
    return list(payload.document_ids)


def _join(*parts: str | None) -> str:
    return "\n\n".join(part for part in parts if part)


def _summary(explanation_en: str) -> str:
    """The explanation's first paragraph: research writes a two-sentence summary,
    a blank line, then the details the date line and checklist repeat (C41). An
    explanation without a blank line is sent whole."""
    return explanation_en.split("\n\n", 1)[0].strip()
