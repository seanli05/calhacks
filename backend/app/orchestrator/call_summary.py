"""The post-call summary (Plan.md → P3, Goal 6.4): the call report, in the user's
language, within 30 s of the call ending.

The next steps are translated free text; the reference number and the new deadlines
go in relay templates, with dates formatted in code, so a translation can't garble
them. If the translation fails, the user gets those templates and an offer to explain,
never English. What to offer next (a retry, closing the case) is the consent gate's.
"""

from app.contracts import CallOutcome, CallReport
from app.contracts.common import CaseId, LanguageCode
from app.db import tables
from app.orchestrator.dates import format_date
from app.relay.outbound import send_template, send_text
from app.relay.templates import render
from app.relay.whatsapp import WhatsApp
from app.translation.translate import Translator, localize


def next_steps_en(report: CallReport) -> str:
    lines = ["Here's how the call with USCIS went:"]
    lines += [f"- {step}" for step in report.next_steps_en]
    return "\n".join(lines)


def fixed_lines(report: CallReport, language: LanguageCode) -> list[str]:
    """The reference number and new deadlines, rendered in `language`."""
    lines = []
    if report.reference_number:
        lines.append(
            render("summary.reference", language, reference=report.reference_number)
        )
    if report.new_deadlines:
        dates = ", ".join(format_date(d, language) for d in report.new_deadlines)
        lines.append(render("summary.deadlines", language, dates=dates))
    return lines


async def send_call_summary(
    whatsapp: WhatsApp,
    translator: Translator | None,
    user: tables.User,
    report: CallReport | None,
    case_id: CaseId,
) -> None:
    """Tell the user how the call went. `report` is None when the call job failed
    without one."""
    if report is None or report.outcome == CallOutcome.FAILED:
        await send_template(whatsapp, user, "summary.call_failed", case_id=case_id)
        return
    if report.outcome == CallOutcome.CANCELLED:
        await send_template(whatsapp, user, "summary.cancelled", case_id=case_id)
        return
    if report.outcome == CallOutcome.USER_UNREACHABLE:
        # The status watcher already said we couldn't reach them (P2).
        await send_template(
            whatsapp, user, "summary.unreachable_followup", case_id=case_id
        )
        return
    language = user.language or "en"
    lead_en = next_steps_en(report) if report.next_steps_en else ""
    lead = await localize(translator, lead_en, language) if lead_en else ""
    if lead is None or not (lead or fixed_lines(report, "en")):
        lead_en = render("summary.unavailable", "en")
        lead = render("summary.unavailable", language)
    body = _join(lead, *fixed_lines(report, language))
    body_en = _join(lead_en, *fixed_lines(report, "en"))
    await send_text(whatsapp, user, body, body_en=body_en, case_id=case_id)


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
