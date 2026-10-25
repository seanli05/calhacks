"""The post-call summary (Plan.md → P3, Goal 6.4): the call report, in the user's
language, within 30 s of the call ending.

The next steps are translated free text; the reference number and the new deadlines
go in relay templates, with dates formatted in code, so a translation can't garble
them. If the translation fails, the user gets those templates and an offer to explain,
never English. What to offer next (a retry, closing the case) is the consent gate's;
it goes at the end of the same message, so the user gets one message, not two.
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


def summary_lead(report: CallReport | None) -> str | None:
    """The template that sums up a call that never reached the user's next steps,
    or None for a report to summarize. `report` is None when the call job failed
    without one."""
    if report is None or report.outcome == CallOutcome.FAILED:
        return "summary.call_failed"
    if report.outcome == CallOutcome.CANCELLED:
        return "summary.cancelled"
    if report.outcome == CallOutcome.USER_UNREACHABLE:
        # The status watcher already said we couldn't reach them (P2).
        return "summary.unreachable_followup"
    return None


async def send_call_summary(
    whatsapp: WhatsApp,
    translator: Translator | None,
    user: tables.User,
    report: CallReport | None,
    case_id: CaseId,
    *,
    suggest_close: bool = False,
) -> None:
    """Tell the user how the call went; with `suggest_close`, the same message
    ends by suggesting they close the letter (C22)."""
    lead_template = summary_lead(report)
    if lead_template is not None or report is None:
        await send_template(whatsapp, user, lead_template, case_id=case_id)
        return
    language = user.language or "en"
    lead_en = next_steps_en(report) if report.next_steps_en else ""
    lead = await localize(translator, lead_en, language) if lead_en else ""
    if lead is None or not (lead or fixed_lines(report, "en")):
        lead_en = render("summary.unavailable", "en")
        lead = render("summary.unavailable", language)
    close = ("summary.suggest_close",) if suggest_close else ()
    body = _join(
        lead,
        *fixed_lines(report, language),
        *(render(t, language) for t in close),
    )
    body_en = _join(
        lead_en, *fixed_lines(report, "en"), *(render(t, "en") for t in close)
    )
    await send_text(whatsapp, user, body, body_en=body_en, case_id=case_id)


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
