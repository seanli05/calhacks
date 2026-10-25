"""The orchestrator's tools for its Claude turn (Plan.md → Orchestrator, C22).

`CaseTools` holds the logic, bound to one user for one turn, so it's testable without
a model; `build_tools` wraps it for the SDK's tool runner. Results are JSON in
English. Sensitive values stay `<ref:...>` placeholders: nothing here resolves a ref
(C11, C34).

`request_consent` only asks: there's no `start_call` tool. A call starts only from
the user's own YES (rule 4): a bare "1" in code, or words the `answer_call_consent`
tool relays, which the consent gate checks against the user's latest message
(consent.py, C43). Research starts from photos, so there's no `start_research` tool.

The `answer_*` tools answer whatever numbered question is open (open_questions.py)
when the user answers in words. Each refuses, with the reason, when the move isn't
legal right now.
"""

import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from anthropic import beta_async_tool
from anthropic.lib.tools import BetaAsyncFunctionTool
from pydantic import ValidationError

from app.contracts import (
    CallReport,
    Component,
    Event,
    EventType,
    FactStatus,
    FastResult,
    FastResultStatus,
    Verification,
)
from app.contracts.common import CallState, CaseId
from app.db import reads, tables
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow
from app.db.writes import orchestrator as writes
from app.orchestrator.consent import ConsentGate
from app.orchestrator.open_questions import OpenQuestions, QuestionKind
from app.phone.control import (
    HangUpResult,
    ListenInResult,
    request_hang_up,
    request_listen_in,
)
from app.relay.outbound import send_template
from app.relay.templates import LANGUAGES
from app.relay.whatsapp import WhatsApp

if TYPE_CHECKING:
    from app.orchestrator.fact_consent import FactConsent
    from app.orchestrator.research_questions import ResearchQuestions
    from app.relay.ask_user import AskUser

logger = logging.getLogger(__name__)

# R1 fields the orchestrator may explain; `proposed_facts` and `key_facts` values
# aren't the user's to read here.
_LETTER_FIELDS = ("doc_type", "issuer", "deadline", "what_is_asked", "urgency")
# In place of stored data that no longer validates (rows from before a contract
# change): the turn goes on without it.
NOT_AVAILABLE = "not available"
_CALL_OVER = frozenset({CallState.WRAP_UP, CallState.ENDED})
_LISTEN_NOTES: dict[ListenInResult, str] = {
    "ringing": "We're calling the user's phone now. They press any key to listen; "
    "the office can't hear them, and hanging up doesn't stop the call. If a "
    "representative answers while they listen, they're joined to talk. Tell them "
    "briefly.",
    "already_listening": "Their phone is already on the call, or ringing for it.",
    "rep_on_line": "A representative is on the line, so the user is being called "
    "(or is already on) to speak with them.",
    "call_over": "The call has ended.",
}
# After an answer tool that sent its own confirmation.
_CONFIRMED = (
    "The user was sent a confirmation. Reply only to the rest of their message; if "
    "there's nothing else in it, reply with no text at all."
)
_HANG_UP_NOTES: dict[HangUpResult, str] = {
    "ending": "The call is being ended now. Tell the user in a few words; a short "
    "message confirming it follows on its own.",
    "call_over": "The call had already ended.",
}


class CaseTools:
    def __init__(
        self,
        user: tables.User,
        whatsapp: WhatsApp,
        consent: ConsentGate | None = None,
        research_questions: "ResearchQuestions | None" = None,
        *,
        ask_user: "AskUser | None" = None,
        fact_consent: "FactConsent | None" = None,
        open_questions: OpenQuestions | None = None,
    ) -> None:
        self.user = user
        self._whatsapp = whatsapp
        self._consent = consent
        self._research_questions = research_questions
        self._ask_user = ask_user
        self._fact_consent = fact_consent
        self._open = open_questions or OpenQuestions()
        self.language_switched = False
        self.consent_requested = False
        # An answer tool sent the user its own confirmation.
        self.answer_confirmed = False

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
                "letter": _letter(case),
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

    async def answer_call_question(self, question_id: str, choice: int) -> str:
        open_question = self._open.of(QuestionKind.CALL_QUESTION)
        if (
            self._ask_user is None
            or open_question is None
            or open_question.ref != question_id
        ):
            return _json({"error": f"No call question {question_id} is open."})
        question = await reads.get_open_question(self.user.id)
        if question is None or question.id != question_id:
            return _json({"error": "That question has closed; the call moved on."})
        if not 1 <= choice <= len(question.options_en):
            return _json(
                {"error": f"Choose a number from 1 to {len(question.options_en)}."}
            )
        if not await self._ask_user.answer(self.user, question, choice):
            self.answer_confirmed = True
            return _json(
                {
                    "error": "The question had already timed out, and the default "
                    "was taken. The user was told which.",
                    "note": _CONFIRMED,
                }
            )
        logger.info(
            "Call question answered by the turn user_id=%s question_id=%s",
            self.user.id,
            question_id,
        )
        return _json(
            {
                "answered": question_id,
                "choice": choice,
                "note": "The call goes on with that option. Tell the user in a few "
                "words, and answer the rest of their message.",
            }
        )

    async def answer_call_consent(
        self, case_id: CaseId, answer: Literal["yes", "no"], user_words: str
    ) -> str:
        if self._consent is None:
            return _json({"error": "Calls aren't available right now."})
        if answer not in ("yes", "no"):
            return _json({"error": 'answer must be "yes" or "no".'})
        refusal = await self._consent.answer_in_words(
            self.user, case_id, 1 if answer == "yes" else 2, user_words
        )
        if refusal is not None:
            return _json({"error": refusal})
        self.answer_confirmed = True
        return _json({"answered": case_id, "answer": answer, "note": _CONFIRMED})

    async def answer_same_or_new(
        self, choice: Literal["same_letter", "new_letter"]
    ) -> str:
        settle = self._open.settle_same_or_new
        if settle is None or choice not in ("same_letter", "new_letter"):
            return _json({"error": 'No "same letter or new?" question is open.'})
        if not await settle(self.user, 1 if choice == "same_letter" else 2):
            return _json({"error": 'No "same letter or new?" question is open.'})
        self.answer_confirmed = True
        return _json({"answered": choice, "note": _CONFIRMED})

    async def answer_save_facts(self, answer: Literal["yes", "no"]) -> str:
        facts = self._fact_consent
        if facts is None or facts.pending(self.user.id) is None:
            return _json({"error": 'No "may I save this?" question is open.'})
        if answer not in ("yes", "no"):
            return _json({"error": 'answer must be "yes" or "no".'})
        await facts.answer(self.user, 1 if answer == "yes" else 2)
        self.answer_confirmed = True
        return _json({"answered": answer, "note": _CONFIRMED})

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

    async def listen_to_call(self, case_id: CaseId) -> str:
        case = await self._own_case(case_id)
        if case is None:
            return _json({"error": f"No case {case_id} for this user."})
        live = await self._live_call(case.id)
        if live is None:
            return _json({"error": "No call is running for this letter right now."})
        result = request_listen_in(live.id)
        logger.info(
            "Listen-in user_id=%s case_id=%s call_id=%s: %s",
            self.user.id,
            case.id,
            live.id,
            result,
        )
        return _json({"listen_in": result, "note": _LISTEN_NOTES[result]})

    async def hang_up_call(self, case_id: CaseId) -> str:
        case = await self._own_case(case_id)
        if case is None:
            return _json({"error": f"No case {case_id} for this user."})
        live = await self._live_call(case.id)
        if live is None:
            return _json({"error": "No call is running for this letter right now."})
        result = request_hang_up(live.id)
        logger.info(
            "Hang-up user_id=%s case_id=%s call_id=%s: %s",
            self.user.id,
            case.id,
            live.id,
            result,
        )
        return _json({"hang_up": result, "note": _HANG_UP_NOTES[result]})

    async def _live_call(self, case_id: CaseId) -> tables.Call | None:
        calls = await reads.list_calls(case_id)
        return next((c for c in reversed(calls) if c.state not in _CALL_OVER), None)

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
    async def listen_to_call(case_id: str) -> str:
        """Ring the user's phone so they can listen in on our call to USCIS while it
        runs (the menus, the hold), muted. Use it when they ask to listen, sit in,
        or be dialed into a call that's under way.

        Args:
            case_id: A case ID from list_active_cases.
        """
        return await tools.listen_to_call(case_id)

    @beta_async_tool
    async def hang_up_call(case_id: str) -> str:
        """End our call to USCIS right away. Only when the user clearly asks to hang
        up or stop the call that's under way; if you're unsure, ask them first.

        Args:
            case_id: A case ID from list_active_cases.
        """
        return await tools.hang_up_call(case_id)

    @beta_async_tool
    async def answer_call_question(question_id: str, choice: int) -> str:
        """Answer the call's open question (call_question in <open_questions>) for
        the user, when their latest message picks one of its options in words
        ("the first one", "about my appointment"). The call is waiting on it.

        Args:
            question_id: The question_id from <open_questions>.
            choice: The option's number, from 1.
        """
        return await tools.answer_call_question(question_id, choice)

    @beta_async_tool
    async def answer_call_consent(
        case_id: str, answer: Literal["yes", "no"], user_words: str
    ) -> str:
        """Record the user's answer to the open call question (call_consent in
        <open_questions>), when their latest message clearly agrees to this call
        or clearly declines it in words. Never for a hedge or a question ("maybe",
        "what will you say?"), and never from an earlier message.

        Args:
            case_id: The case_id from <open_questions>.
            answer: "yes" to make the call, "no" not to.
            user_words: The words in the user's latest message that give the
                answer, copied exactly as they appear in it.
        """
        return await tools.answer_call_consent(case_id, answer, user_words)

    @beta_async_tool
    async def answer_same_or_new(choice: Literal["same_letter", "new_letter"]) -> str:
        """Answer "same letter or new?" (same_or_new in <open_questions>) when the
        user says in words whether their latest photos are more pages of the same
        letter or a new letter.

        Args:
            choice: "same_letter" or "new_letter".
        """
        return await tools.answer_same_or_new(choice)

    @beta_async_tool
    async def answer_save_facts(answer: Literal["yes", "no"]) -> str:
        """Answer "may I save this?" (save_facts in <open_questions>) when the
        user clearly says in words whether we may remember those facts.

        Args:
            answer: "yes" to save them, "no" not to.
        """
        return await tools.answer_save_facts(answer)

    @beta_async_tool
    async def set_language(language: str) -> str:
        """Switch the language the user is written to in, when they ask for it.

        Args:
            language: ISO 639-1 code: "es" (Spanish), "en" (English), or "fa"
                (Dari; also for Farsi or Persian).
        """
        return await tools.set_language(language)

    return [
        list_active_cases,
        get_case_status,
        get_profile,
        close_case,
        request_consent,
        ask_official_source,
        listen_to_call,
        hang_up_call,
        answer_call_question,
        answer_call_consent,
        answer_same_or_new,
        answer_save_facts,
        set_language,
    ]


def _letter(case: tables.Case) -> dict[str, Any] | str | None:
    if not case.fast_result:
        return None
    try:
        result = FastResult.model_validate(case.fast_result)
    except ValidationError:
        logger.exception("Bad stored R1 case_id=%s", case.id)
        return NOT_AVAILABLE
    if result.status == FastResultStatus.NEEDS_BETTER_IMAGE:
        return {"status": str(result.status), "tip": result.image_issue}
    letter = result.model_dump(mode="json", include=set(_LETTER_FIELDS))
    letter["explanation"] = result.explanation_en
    if result.appointment is not None:
        letter["appointment"] = {
            "date": result.appointment.date.isoformat(),
            "time": result.appointment.time,
            "location": result.appointment.location_ref,
        }
    letter["checklist"] = [
        {"kind": str(item.kind), "item": item.item} for item in result.checklist_en
    ]
    letter["identifiers_on_letter"] = [
        fact.field for fact in result.key_facts if fact.ref
    ]
    return letter


def _verification(row: tables.Verification | None) -> dict[str, Any]:
    if row is None:
        return {"status": "pending"}
    try:
        result = Verification.model_validate(row.result)
    except ValidationError:
        logger.exception("Bad stored verification case_id=%s", row.case_id)
        return {"status": str(row.status), "red_flags": NOT_AVAILABLE}
    return {"status": str(row.status), "red_flags": result.red_flags}


def _call(call: tables.Call) -> dict[str, Any]:
    """The call's state and, once it has ended, what the report says to tell the
    user (P3)."""
    status: dict[str, Any] = {"state": str(call.state)}
    if call.report is None:
        return status | {
            "outcome": None,
            "reference_number": None,
            "next_steps": [],
            "new_deadlines": [],
        }
    try:
        report = CallReport.model_validate(call.report)
    except ValidationError:
        logger.exception(
            "Bad stored call report case_id=%s call_id=%s job_id=%s",
            call.case_id,
            call.id,
            call.job_id,
        )
        return status | {"report": NOT_AVAILABLE}
    return status | {
        "outcome": str(report.outcome),
        "reference_number": report.reference_number,
        "next_steps": report.next_steps_en,
        "new_deadlines": [d.isoformat() for d in report.new_deadlines],
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
