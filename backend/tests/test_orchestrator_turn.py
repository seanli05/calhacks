"""The orchestrator's Claude turn (Goal 4.1, 4.5) and its tools, on fakes: no
Anthropic, no Twilio, no database."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from app.contracts import (
    AskUserRequest,
    CallState,
    EventType,
    FactStatus,
    JobType,
    Sensitivity,
    VerificationStatus,
)
from app.db import tables
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.tools import CaseTools
from app.orchestrator.turn import UNAVAILABLE, OrchestratorTurn
from app.relay.ask_user import AskUser
from app.relay.templates import render
from whatsapp_fakes import FakeDB, FakeWhatsApp, inbound, use_spanish

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def fast_result(case_id: str) -> dict[str, Any]:
    r1 = json.loads((FIXTURES / "fast_result.json").read_text(encoding="utf-8"))
    return {**r1, "case_id": case_id}


async def letter_case(db: FakeDB, user: tables.User) -> tables.Case:
    case = tables.Case(user_id=user.id, doc_type="uscis_i797c_asylum_interview")
    case.fast_result = fast_result(case.id)
    db.cases.append(case)
    return case


# Tools


async def test_case_status_explains_the_letter_and_keeps_refs(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    case = await letter_case(db, user)
    deep = json.loads((FIXTURES / "deep_result.json").read_text(encoding="utf-8"))
    db.verifications[case.id] = tables.Verification(
        case_id=case.id,
        status=VerificationStatus.VERIFIED,
        result=deep["verification"],
    )

    status = json.loads(await CaseTools(user, whatsapp).get_case_status(case.id))

    assert status["stage"] == "awaiting_consent"
    assert status["verification"] == {"status": "verified", "red_flags": []}
    letter = status["letter"]
    assert letter["doc_type"] == "uscis_i797c_asylum_interview"
    assert letter["explanation"]
    assert letter["appointment"] == {
        "date": "2026-11-18",
        "time": "08:30",
        "location": "<ref:interview_location>",
    }
    assert {item["kind"] for item in letter["checklist"]} == {
        "who_must_come",
        "bring",
        "deadline",
    }
    assert letter["identifiers_on_letter"] == ["receipt_number", "a_number"]
    assert "proposed_facts" not in letter


def ended_call(case: tables.Case, report: dict[str, Any]) -> tables.Call:
    return tables.Call(
        case_id=case.id,
        job_id="job_1",
        brief_id="brief_1",
        consent_message_id="msg_1",
        state=CallState.ENDED,
        report=report,
    )


async def test_case_status_reads_the_call_report(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    case = await letter_case(db, user)
    report = json.loads((FIXTURES / "call_report.json").read_text(encoding="utf-8"))
    call = ended_call(case, {**report, "case_id": case.id})
    db.calls[call.id] = call

    status = json.loads(await CaseTools(user, whatsapp).get_case_status(case.id))

    assert status["last_call"] == {
        "state": "ended",
        "outcome": "resolved",
        "reference_number": "R-55821",
        "next_steps": report["next_steps_en"],
        "new_deadlines": ["2026-11-17"],
    }


async def test_case_status_survives_rows_that_no_longer_validate(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    """Rows written before a contract change: the turn goes on without them, and
    never resolves a ref."""
    user = await use_spanish(db)
    case = tables.Case(
        user_id=user.id,
        doc_type="uscis_i797c_asylum_interview",
        fast_result={"status": "ok", "issuer": "USCIS", "a_number": "<ref:a_number>"},
    )
    db.cases.append(case)
    db.verifications[case.id] = tables.Verification(
        case_id=case.id, status=VerificationStatus.VERIFIED, result={"red_flags": []}
    )
    call = ended_call(case, {"outcome": "resolved"})
    db.calls[call.id] = call

    status = json.loads(await CaseTools(user, whatsapp).get_case_status(case.id))

    assert status["letter"] == "not available"
    assert status["verification"] == {
        "status": "verified",
        "red_flags": "not available",
    }
    assert status["last_call"] == {"state": "ended", "report": "not available"}


async def test_tools_refuse_another_users_case(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    other = tables.Case(user_id="user_other")
    db.cases.append(other)
    tools = CaseTools(user, whatsapp)

    assert "error" in json.loads(await tools.get_case_status(other.id))
    assert "error" in json.loads(await tools.close_case(other.id))
    assert db.events == []


async def test_close_case_logs_an_event_once(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    case = await letter_case(db, user)
    tools = CaseTools(user, whatsapp)

    assert json.loads(await tools.close_case(case.id)) == {"closed": case.id}
    assert "error" in json.loads(await tools.close_case(case.id))

    [event] = db.events
    assert (event.type, event.case_id, event.source, event.data) == (
        EventType.CASE_CLOSED,
        case.id,
        "orchestrator",
        {},
    )
    assert json.loads(await tools.list_active_cases()) == {"active_cases": []}


async def test_set_language_switches_and_tells_the_user(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    tools = CaseTools(user, whatsapp)

    assert "error" in json.loads(await tools.set_language("fr"))
    assert json.loads(await tools.set_language("es"))["changed"] is False
    assert json.loads(await tools.set_language("EN"))["changed"] is True

    assert user.language == "en"
    assert tools.language_switched
    assert whatsapp.sent == [render("language.set", "en")]


async def test_profile_shows_only_active_facts(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    db.profiles[user.id] = tables.Profile(user_id=user.id, fields={"city": "Oakland"})
    for fact, status in [
        ("Has two children", FactStatus.ACTIVE),
        ("Has an asylum interview scheduled", FactStatus.PENDING_CONSENT),
    ]:
        db.facts.append(
            tables.Fact(
                user_id=user.id,
                fact=fact,
                category="family",
                source="user_said",
                sensitivity=Sensitivity.NORMAL,
                status=status,
            )
        )

    profile = json.loads(await CaseTools(user, whatsapp).get_profile())

    assert profile["profile"] == {"city": "Oakland"}
    assert [f["fact"] for f in profile["facts"]] == ["Has two children"]


# The turn


class FakeTranslator:
    def __init__(self, fail_out: bool = False) -> None:
        self.fail_out = fail_out

    async def to_english(self, text: str, language: str) -> str | None:
        return f"EN({text})"

    async def from_english(self, text_en: str, language: str) -> str | None:
        return None if self.fail_out else f"{language.upper()}({text_en})"


class FakeRunnerClient:
    """Stands in for `client.beta.messages.tool_runner`: optionally calls tools the
    way the model would, then yields one final message."""

    def __init__(
        self,
        reply: str | None = "Your interview is on 2026-11-18 at 08:30.",
        tool_calls: list[tuple[str, dict[str, Any]]] | None = None,
        fail: bool = False,
        stop_reason: str = "end_turn",
    ) -> None:
        self.beta = SimpleNamespace(messages=self)
        self.requests: list[dict[str, Any]] = []
        self.tool_results: list[str] = []
        self._reply = reply
        self._tool_calls = tool_calls or []
        self._fail = fail
        self._stop_reason = stop_reason

    def tool_runner(self, **request: Any) -> Any:
        self.requests.append(request)
        return self._run(request)

    async def _run(self, request: dict[str, Any]) -> Any:
        if self._fail:
            raise anthropic.APITimeoutError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        tools = {tool.name: tool for tool in request["tools"]}
        for name, tool_input in self._tool_calls:
            self.tool_results.append(await tools[name].call(tool_input))
        content = (
            [SimpleNamespace(type="text", text=self._reply)] if self._reply else []
        )
        yield SimpleNamespace(stop_reason=self._stop_reason, content=content)


def make_turn(
    client: FakeRunnerClient,
    whatsapp: FakeWhatsApp,
    translator: FakeTranslator | None = None,
) -> OrchestratorTurn:
    fake_client: Any = client
    fake_translator: Any = translator or FakeTranslator()
    return OrchestratorTurn(fake_client, "model-default", whatsapp, fake_translator)


async def test_turn_replies_in_the_users_language_with_english_logged(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    case = await letter_case(db, user)
    client = FakeRunnerClient(tool_calls=[("get_case_status", {"case_id": case.id})])

    await make_turn(client, whatsapp).run(user, "msg_1")

    reply = db.messages[-1]
    assert (reply.sender, reply.language) == ("orchestrator", "es")
    assert reply.body_original == "ES(Your interview is on 2026-11-18 at 08:30.)"
    assert reply.body_en == "Your interview is on 2026-11-18 at 08:30."
    assert (
        json.loads(client.tool_results[0])["letter"]["appointment"]["time"] == "08:30"
    )
    [request] = client.requests
    assert request["model"] == "model-default"
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert {tool.name for tool in request["tools"]} == {
        "list_active_cases",
        "get_case_status",
        "get_profile",
        "close_case",
        "request_consent",
        "ask_official_source",
        "set_language",
    }  # no start_call: only the user's numbered YES starts one (rule 4)
    # Goal 6.5: the memory writer runs on the user's message after each reply.
    [memory] = db.jobs_of(JobType.MEMORY_WRITE)
    assert memory.payload["source_ref"] == "msg_1"
    assert memory.payload["source"] == "user_said"


async def test_context_is_english_and_never_resolves_refs(
    db: FakeDB, whatsapp: FakeWhatsApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def resolve_ref(*_: object) -> str:
        pytest.fail("the orchestrator must never resolve a ref (C34)")

    monkeypatch.setattr("app.db.reads.resolve_ref", resolve_ref)
    user = await use_spanish(db)
    await letter_case(db, user)
    await db.append_message(
        user.id, "in", "user", "¿Qué dice mi carta?", "es", body_en="What does it say?"
    )
    case = db.cases[0]
    client = FakeRunnerClient(tool_calls=[("get_case_status", {"case_id": case.id})])

    await make_turn(client, whatsapp).run(user, "msg_1")

    assert "<ref:interview_location>" in client.tool_results[0]
    context = client.requests[0]["messages"][0]["content"]
    assert "User: What does it say?" in context
    assert "uscis_i797c_asylum_interview" in context
    assert "<pending>" not in context


@pytest.mark.parametrize(
    ("client", "translator"),
    [
        (FakeRunnerClient(fail=True), FakeTranslator()),
        (FakeRunnerClient(reply=None), FakeTranslator()),
        (FakeRunnerClient(stop_reason="refusal"), FakeTranslator()),
        (FakeRunnerClient(), FakeTranslator(fail_out=True)),
    ],
    ids=["api-error", "no-text", "refusal", "translation-failed"],
)
async def test_failures_send_the_unavailable_template_never_english(
    db: FakeDB,
    whatsapp: FakeWhatsApp,
    client: FakeRunnerClient,
    translator: FakeTranslator,
) -> None:
    user = await use_spanish(db)

    await make_turn(client, whatsapp, translator).run(user, "msg_1")

    assert db.outbound_templates() == [UNAVAILABLE]
    assert whatsapp.sent == [render(UNAVAILABLE, "es")]


async def test_language_switch_sends_only_the_template(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    client = FakeRunnerClient(tool_calls=[("set_language", {"language": "en"})])

    await make_turn(client, whatsapp).run(user, "msg_1")

    assert db.outbound_templates() == ["language.set"]
    assert whatsapp.sent == [render("language.set", "en")]


# Pipe wiring


@pytest.fixture
def wired_pipe(
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Any,
) -> tuple[InboundPipe, list[dict[str, Any]]]:
    turns: list[dict[str, Any]] = []

    async def turn(
        user: tables.User,
        message_id: str,
        *,
        same_or_new_pending: bool = False,
        consent_pending: bool = False,
    ) -> None:
        turns.append({"user": user.id, "pending": same_or_new_pending})

    async def detect(text: str) -> None:
        return None

    wired = InboundPipe(
        whatsapp,
        detect,
        ask_user,
        letters,
        quiet_window_s=0.05,
        to_english=FakeTranslator().to_english,
        turn=turn,
    )
    return wired, turns


async def test_spanish_text_is_logged_with_english_and_reaches_the_turn(
    db: FakeDB, wired_pipe: tuple[InboundPipe, list[dict[str, Any]]]
) -> None:
    pipe, turns = wired_pipe
    user = await use_spanish(db)

    await pipe.handle(inbound("¿Qué dice mi carta?"))

    assert db.messages[0].body_en == "EN(¿Qué dice mi carta?)"
    assert turns == [{"user": user.id, "pending": False}]


async def test_reply_to_an_open_question_is_not_translated(
    db: FakeDB,
    wired_pipe: tuple[InboundPipe, list[dict[str, Any]]],
    ask_user: AskUser,
) -> None:
    pipe, turns = wired_pipe
    user = await use_spanish(db)
    call = db.add_call(user)
    await db.create_question(
        AskUserRequest(
            question_id="question_1",
            call_id=call.id,
            template="menu_choice",
            options_en=["A", "B"],
            default_option=1,
            timeout_s=45,
        ),
        user.id,
    )

    await pipe.handle(inbound("2"))

    assert db.messages[0].body_en == "2"  # a bare number needs no model call
    assert turns == []


async def test_text_while_same_or_new_is_pending_goes_to_the_turn(
    db: FakeDB, wired_pipe: tuple[InboundPipe, list[dict[str, Any]]]
) -> None:
    pipe, turns = wired_pipe
    user = await use_spanish(db)
    letter = await db.create_document(user.id, ["media_old"])
    db.cases.append(tables.Case(user_id=user.id, document_ids=[letter.id]))

    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound("¿cuál es la diferencia?"))

    assert db.outbound_templates() == ["letter.same_or_new"]
    assert turns == [{"user": user.id, "pending": True}]
    await pipe.handle(inbound("1"))
    assert db.outbound_templates()[-1] == "letter.pages_added"
