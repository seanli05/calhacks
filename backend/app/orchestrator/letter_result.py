"""Turning R1 into the user's explanation (Plan.md → R1, C9, C31; Goal 6.1).

One message: the explanation, the interview date and time, the checklist (who must
come, what to bring, other deadlines), and "I'm checking that this letter is
legitimate". The explanation and checklist are translated free text (in parallel);
the date line and the closing are relay templates, with the date formatted in code,
so the one fact that must survive is never left to a model. If translation fails,
the user gets the templates and an offer to explain, never English.

Once it's sent, the case's deep pass is watched for the verdict (verdicts.py), so the
verdict never overtakes the explanation.
"""

import asyncio
import logging

from pydantic import ValidationError

from app.contracts import ChecklistKind, FastResult, FastResultStatus
from app.contracts.common import LanguageCode
from app.db import reads, tables
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


class LetterResults:
    def __init__(
        self, whatsapp: WhatsApp, translator: Translator | None, verdicts: Verdicts
    ) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._verdicts = verdicts

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
        readable = result.status != FastResultStatus.NEEDS_BETTER_IMAGE
        try:
            if readable:
                await self._explain(user, result)
            else:
                await self._retake(user, result)
        except WhatsAppSendError as exc:
            logger.error(
                "Letter result not sent case_id=%s job_id=%s: %s",
                result.case_id,
                job.id,
                exc,
            )
        if readable:
            self._verdicts.watch(user.id, result.case_id, since=job.created_at)

    async def _explain(self, user: tables.User, result: FastResult) -> None:
        language = user.language or "en"
        explanation_en = result.explanation_en or ""
        checklist = checklist_en(result)
        explanation, translated_checklist = await asyncio.gather(
            self._localize(explanation_en, language),
            self._localize(checklist, language),
        )
        if explanation is None or translated_checklist is None:
            logger.warning("Explanation not translated case_id=%s", result.case_id)
            body = _join(
                render("letter.explain_failed", language),
                date_line(result, language),
                render("letter.checking", language),
            )
            body_en = _join(
                render("letter.explain_failed", "en"),
                date_line(result, "en"),
                render("letter.checking", "en"),
            )
        else:
            body = _join(
                explanation,
                date_line(result, language),
                translated_checklist,
                render("letter.checking", language),
            )
            body_en = _join(
                explanation_en,
                date_line(result, "en"),
                checklist,
                render("letter.checking", "en"),
            )
        await send_text(
            self._whatsapp, user, body, body_en=body_en, case_id=result.case_id
        )
        logger.info("Explanation sent case_id=%s", result.case_id)

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

    async def _localize(self, text_en: str, language: LanguageCode) -> str | None:
        if not text_en:
            return ""
        return await localize(self._translator, text_en, language)


def _join(*parts: str | None) -> str:
    return "\n\n".join(part for part in parts if part)
