"""The orchestrator's tools for its Claude turn (Plan.md → Orchestrator, C22).

`CaseTools` holds the logic, bound to one user for one turn, so it's testable without
a model; `build_tools` wraps it for the SDK's tool runner. Results are JSON in
English. Sensitive values stay `<ref:...>` placeholders: nothing here resolves a ref
(C11, C34).

`request_consent` only asks: there's no `start_call` tool, because a call starts
only from the user's own numbered YES, in code (consent.py, rule 4). Research starts
from photos, so there's no `start_research` tool.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

from anthropic import beta_async_tool
from anthropic.lib.tools import BetaAsyncFunctionTool

from app.contracts import Component, Event, EventType, FactStatus
from app.contracts.common import CaseId
from app.db import reads, tables
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow
from app.db.writes import orchestrator as writes
from app.orchestrator.consent import ConsentGate
from app.relay.outbound import send_template
from app.relay.templates import LANGUAGES
from app.relay.whatsapp import WhatsApp

if TYPE_CHECKING:
    from app.orchestrator.research_questions import ResearchQuestions

logger = logging.getLogger(__name__)

# R1 fields the orchestrator may explain; `proposed_facts` and `key_facts` values
# aren't the user's to read here.
_LETTER_FIELDS = ("doc_type", "issuer", "deadline", "what_is_asked", "urgency")


class CaseTools:
    def __init__(
        self,
        user: tables.User,
        whatsapp: WhatsApp,
        consent: ConsentGate | None = None,
        research_questions: "ResearchQuestions | None" = None,
    ) -> None:
        self.user = user
        self._whatsapp = whatsapp
        self._consent = consent
        self._research_questions = research_questions
        self.language_switched = False
        self.consent_requested = False

    async def list_active_cases(self) -> str:
        cases = []
        for case in await reads.list_active_cases(self.user.id):
            cases.append(
                {
                    "case_id": case.id,
                    "doc_type": case.doc_type,
                    "deadline": case.deadline.isoformat() if case.deadline else None,
                    "stage": str(await reads.case_progress(case.id)),
                    "opened": case.created_at.date().isoformat(),
                }
            )
        return _json({"active_cases": cases})

    async def get_case_status(self, case_id: CaseId) -> str:
        case = await self._own_case(case_id)
        if case is None:
            return _json({"error": f"No case {case_id} for this user."})
        verification = await reads.latest_verification(case.id)
        calls = await reads.list_calls(case.id)
        return _json(
            {
                "case_id": case.id,
                "stage": str(await reads.case_progress(case.id)),
                "letter": _letter(case.fast_result),
                "verification": _verification(verification),
                "last_call": _call(calls[-1]) if calls else None,
            }
        )

    async def get_profile(self) -> str:
        profile = await reads.get_profile(self.user.id)
        facts = await reads.list_facts(self.user.id, [FactStatus.ACTIVE])
        return _json(
            {
                "language": self.user.language,
                "profile": profile.fields if profile else {},
                "facts": [{"fact": f.fact, "category": f.category} for f in facts],
            }
        )

    async def close_case(self, case_id: CaseId) -> str:
        case = await self._own_case(case_id)
        if case is None:
            return _json({"error": f"No case {case_id} for this user."})
        active = {c.id for c in await reads.list_active_cases(self.user.id)}
        if case.id not in active:
            return _json({"error": f"Case {case_id} is already closed."})
        await append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=EventType.CASE_CLOSED,
                source=Component.ORCHESTRATOR,
                user_id=self.user.id,
                case_id=case.id,
                summary_en="Closed the case at the user's request",
            )
        )
        logger.info("Case closed user_id=%s case_id=%s", self.user.id, case.id)
        return _json({"closed": case.id})

    async def set_language(self, language: str) -> str:
        code = language.strip().lower()
        if code not in LANGUAGES:
            return _json(
                {"error": f"Unsupported language {language!r}.", "supported": LANGUAGES}
            )
        if code == self.user.language:
            return _json({"language": code, "changed": False})
        self.user = await writes.set_language(self.user.id, code)
        await send_template(self._whatsapp, self.user, "language.set")
        self.language_switched = True
        logger.info("Language switched user_id=%s language=%s", self.user.id, code)
        return _json(
            {
                "language": code,
                "changed": True,
                "note": "The user was told in the new language. Don't reply further.",
            }
        )

    async def request_consent(self, case_id: CaseId) -> str:
        if self._consent is None:
            return _json({"error": "Calls aren't available right now."})
        refusal = await self._consent.request(self.user, case_id)
        if refusal is not None:
            return _json({"error": refusal})
        self.consent_requested = True
        return _json(
            {
                "asked": case_id,
                "note": "The user was sent a yes/no question about the call. Don't "
                "reply further.",
            }
        )

    async def ask_official_source(self, question: str, case_id: str | None) -> str:
        if self._research_questions is None:
            return _json({"error": "Looking things up isn't available right now."})
        question = question.strip()
        if not question:
            return _json({"error": "The question is empty."})
        if case_id and await self._own_case(case_id) is None:
            return _json({"error": f"No case {case_id} for this user."})
        await self._research_questions.ask(self.user, question, case_id or None)
        return _json(
            {
                "queued": True,
                "note": "The answer, with its official sources, is sent to the user "
                "on its own in a minute or two. Tell them you're looking it up on "
                "official sites; don't answer the question yourself.",
            }
        )

    async def _own_case(self, case_id: CaseId) -> tables.Case | None:
        case = await reads.get_case(case_id)
        return case if case is not None and case.user_id == self.user.id else None


def build_tools(tools: CaseTools) -> list[BetaAsyncFunctionTool[Any]]:
    """The runner's tool list for one turn. Docstrings become the tool descriptions."""

    @beta_async_tool
    async def list_active_cases() -> str:
        """The user's open letters (cases): ID, document type, deadline, and stage."""
        return await tools.list_active_cases()

    @beta_async_tool
    async def get_case_status(case_id: str) -> str:
        """One case's stage, what its letter says (explanation, appointment date
        and time, checklist, deadline), and whether it was verified as legitimate.

        Args:
            case_id: A case ID from list_active_cases.
        """
        return await tools.get_case_status(case_id)

    @beta_async_tool
    async def get_profile() -> str:
        """What the user has agreed we may remember about them."""
        return await tools.get_profile()

    @beta_async_tool
    async def close_case(case_id: str) -> str:
        """Close a letter so it's no longer active. Only when the user asked to, or
        agreed when you offered.

        Args:
            case_id: A case ID from list_active_cases.
        """
        return await tools.close_case(case_id)

    @beta_async_tool
    async def request_consent(case_id: str) -> str:
        """Ask the user whether we may call USCIS about this letter. Sends them a
        yes/no question; the call starts only if they answer yes. Use it when the
        user asks for a call, or to offer one again. It refuses if the letter
        isn't verified or a call is already under way.

        Args:
            case_id: A case ID from list_active_cases.
        """
        return await tools.request_consent(case_id)

    @beta_async_tool
    async def ask_official_source(question: str, case_id: str = "") -> str:
        """Look up a factual question about the user's letter or the immigration
        process on official government sites (C38), when your tools don't already
        answer it. Not for legal advice or anything about their asylum claim. The
        answer is sent to the user separately, with its sources.

        Args:
            question: The question in plain English, self-contained.
            case_id: The case it's about, from list_active_cases, or "" if none.
        """
        return await tools.ask_official_source(question, case_id or None)

    @beta_async_tool
    async def set_language(language: str) -> str:
        """Switch the language the user is written to in, when they ask for it.

        Args:
            language: ISO 639-1 code, e.g. "es" or "en".
        """
        return await tools.set_language(language)

    return [
        list_active_cases,
        get_case_status,
        get_profile,
        close_case,
        request_consent,
        ask_official_source,
        set_language,
    ]


def _letter(fast_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not fast_result:
        return None
    if fast_result.get("status") == "needs_better_image":
        return {"status": "needs_better_image", "tip": fast_result.get("image_issue")}
    letter = {field: fast_result.get(field) for field in _LETTER_FIELDS}
    letter["explanation"] = fast_result.get("explanation_en")
    appointment = fast_result.get("appointment")
    if appointment:
        letter["appointment"] = {
            "date": appointment.get("date"),
            "time": appointment.get("time"),
            "location": appointment.get("location_ref"),
        }
    letter["checklist"] = [
        {"kind": item.get("kind"), "item": item.get("item")}
        for item in fast_result.get("checklist_en", [])
    ]
    letter["identifiers_on_letter"] = [
        fact.get("field")
        for fact in fast_result.get("key_facts", [])
        if fact.get("ref")
    ]
    return letter


def _verification(row: tables.Verification | None) -> dict[str, Any]:
    if row is None:
        return {"status": "pending"}
    result = row.result or {}
    return {"status": str(row.status), "red_flags": result.get("red_flags", [])}


def _call(call: tables.Call) -> dict[str, Any]:
    """The call's state and, once it has ended, what the report says to tell the
    user (P3)."""
    report = call.report or {}
    return {
        "state": str(call.state),
        "outcome": report.get("outcome"),
        "reference_number": report.get("reference_number"),
        "next_steps": report.get("next_steps_en", []),
        "new_deadlines": report.get("new_deadlines", []),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
