"""The orchestrator's `listen_to_call` and `hang_up_call` tools: they ask the phone
agent about the case's live call, and only for the user's own case."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from app.orchestrator import tools as orchestrator_tools
from app.orchestrator.tools import CaseTools


@pytest.fixture
def tool_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "asked": [], "ended": []}

    async def get_case(case_id: str) -> Any:
        owner = "user_9" if case_id == "case_1" else "user_other"
        return SimpleNamespace(id=case_id, user_id=owner)

    async def list_calls(case_id: str) -> list[Any]:
        return state["calls"]

    def request(call_id: str) -> str:
        state["asked"].append(call_id)
        return "ringing"

    def hang_up(call_id: str) -> str:
        state["ended"].append(call_id)
        return "ending"

    monkeypatch.setattr(orchestrator_tools.reads, "get_case", get_case)
    monkeypatch.setattr(orchestrator_tools.reads, "list_calls", list_calls)
    monkeypatch.setattr(orchestrator_tools, "request_listen_in", request)
    monkeypatch.setattr(orchestrator_tools, "request_hang_up", hang_up)
    return state


def _tools() -> CaseTools:
    return CaseTools(SimpleNamespace(id="user_9"), whatsapp=None)  # type: ignore[arg-type]


async def test_the_tool_asks_for_the_cases_live_call(
    tool_reads: dict[str, Any],
) -> None:
    tool_reads["calls"] = [
        SimpleNamespace(id="call_old", state="ended"),
        SimpleNamespace(id="call_live", state="hold"),
    ]
    result = json.loads(await _tools().listen_to_call("case_1"))

    assert result["listen_in"] == "ringing"
    assert tool_reads["asked"] == ["call_live"]


async def test_the_tool_refuses_without_a_live_call_or_for_another_users_case(
    tool_reads: dict[str, Any],
) -> None:
    tool_reads["calls"] = [SimpleNamespace(id="call_old", state="ended")]
    assert "error" in json.loads(await _tools().listen_to_call("case_1"))
    assert "error" in json.loads(await _tools().listen_to_call("case_2"))
    assert tool_reads["asked"] == []


async def test_hang_up_ends_the_cases_live_call(tool_reads: dict[str, Any]) -> None:
    tool_reads["calls"] = [SimpleNamespace(id="call_live", state="menu")]
    result = json.loads(await _tools().hang_up_call("case_1"))

    assert result["hang_up"] == "ending"
    assert tool_reads["ended"] == ["call_live"]


async def test_hang_up_refuses_another_users_case_or_no_live_call(
    tool_reads: dict[str, Any],
) -> None:
    tool_reads["calls"] = [SimpleNamespace(id="call_live", state="hold")]
    assert "error" in json.loads(await _tools().hang_up_call("case_2"))
    tool_reads["calls"] = [SimpleNamespace(id="call_old", state="ended")]
    assert "error" in json.loads(await _tools().hang_up_call("case_1"))
    assert tool_reads["ended"] == []
