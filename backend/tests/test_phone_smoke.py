"""The live smoke test's guard rails (`phone/smoke.py`): it dials only the mock
line or your own phone, rings only your own phone and only with `--bridge`, and
the app never imports it."""

import ast
import json
import subprocess
from pathlib import Path

import pytest
from app.contracts.common import CallState
from app.db.errors import UnverifiedNumber
from app.phone.fakes import FakeNumberSource
from app.phone.line import Heard
from app.phone.menu import PressAction
from app.phone.observe import StepRecord
from app.phone.phase import Phase, PhaseReading
from app.phone.smoke import (
    RUNS_DIR,
    MockLineOnly,
    Printer,
    SmokeNumberSource,
    SmokeRefused,
)

MOCK = "+15672298566"
YOU = "+15555550123"
APP = Path(__file__).resolve().parents[1] / "app"


async def test_the_mock_line_is_passed_on() -> None:
    numbers = MockLineOnly(FakeNumberSource({"case_1": MOCK}), MOCK)
    assert await numbers.official_dial_number("case_1") == MOCK


async def test_any_other_verified_number_is_refused_without_naming_it() -> None:
    numbers = MockLineOnly(FakeNumberSource({"case_1": "+18003755283"}), MOCK)
    with pytest.raises(SmokeRefused) as refused:
        await numbers.official_dial_number("case_1")
    assert "+1800" not in str(refused.value)


async def test_an_unverified_case_still_gets_no_number() -> None:
    numbers = MockLineOnly(FakeNumberSource({}), MOCK)
    with pytest.raises(UnverifiedNumber):
        await numbers.official_dial_number("case_1")


async def test_no_mock_number_set_means_nothing_is_dialed() -> None:
    numbers = MockLineOnly(FakeNumberSource({"case_1": ""}), "")
    with pytest.raises(SmokeRefused):
        await numbers.official_dial_number("case_1")


async def test_without_bridge_the_smoke_test_never_rings_anyone() -> None:
    for numbers in (MockLineOnly(FakeNumberSource(), MOCK), SmokeNumberSource(MOCK)):
        with pytest.raises(SmokeRefused):
            await numbers.user_number("user_9")


async def test_with_bridge_it_rings_only_your_own_phone() -> None:
    db_users = FakeNumberSource(users={"user_9": "+15550000001"})
    for numbers in (
        MockLineOnly(db_users, MOCK, applicant=YOU),
        SmokeNumberSource(MOCK, applicant=YOU),
    ):
        assert await numbers.user_number("user_9") == YOU


def test_your_applicant_number_must_be_e164_and_isnt_echoed() -> None:
    with pytest.raises(SmokeRefused) as refused:
        MockLineOnly(FakeNumberSource(), MOCK, applicant="555-1234")
    assert "555-1234" not in str(refused.value)


def test_your_own_number_must_be_e164() -> None:
    with pytest.raises(SmokeRefused):
        SmokeNumberSource("555-1234")


def test_nothing_in_the_app_imports_the_smoke_test() -> None:
    importers = []
    for path in APP.rglob("*.py"):
        if path.name == "smoke.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in getattr(node, "names", [])]
                if isinstance(node, ast.Import)
                else []
            )
            if any(name.endswith("phone.smoke") for name in names) or (
                isinstance(node, ast.ImportFrom)
                and node.module == "app.phone"
                and any(alias.name == "smoke" for alias in node.names)
            ):
                importers.append(str(path.relative_to(APP)))
    assert importers == []


def test_a_run_is_printed_in_full_and_saved_as_json_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = StepRecord(
        at_s=4.2,
        input="timer:menu_quiet",
        text="For an interview you have scheduled, press 2.",
        state_before=CallState.MENU,
        state_after=CallState.MENU,
        reading=PhaseReading(
            phase=Phase.MENU,
            confidence=0.93,
            reason_en="Keypad options",
            source="model",
        ),
        action=PressAction(
            kind="press", digits="2", option_label_en="interview", reason_en="Fits"
        ),
        sent=["speech: two"],
        latency_ms={"classify": 640, "decide": 910},
        flags=["held"],
    )
    run_file = tmp_path / "smoke_runs" / "run.jsonl"
    out = Printer(run_file)
    out.event(Heard(text="Please hold."))
    out.step(record)
    out.close()

    printed = capsys.readouterr().out
    for shown in ("menu 0.93 (model)", "Fits", "speech: two", "decide 910 ms", "held"):
        assert shown in printed
    rows = [json.loads(row) for row in run_file.read_text().splitlines()]
    assert [row["kind"] for row in rows] == ["line_event", "step"]
    assert rows[0]["event"] == {"kind": "heard", "text": "Please hold."}
    assert rows[1]["record"]["sent"] == ["speech: two"]


def test_saved_runs_are_never_committed() -> None:
    assert RUNS_DIR.name == "smoke_runs"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(RUNS_DIR / "any.jsonl")],
        cwd=APP.parent,
        check=False,
    )
    assert ignored.returncode == 0
