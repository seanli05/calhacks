"""The live smoke test's guard rails (`phone/smoke.py`): it dials only the mock
line or your own phone, never rings anyone else, and the app never imports it."""

import ast
from pathlib import Path

import pytest
from app.db.errors import UnverifiedNumber
from app.phone.fakes import FakeNumberSource
from app.phone.smoke import MockLineOnly, SmokeNumberSource, SmokeRefused

MOCK = "+15672298566"
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


async def test_the_smoke_test_never_rings_anyone() -> None:
    for numbers in (MockLineOnly(FakeNumberSource(), MOCK), SmokeNumberSource(MOCK)):
        with pytest.raises(SmokeRefused):
            await numbers.user_number("user_9")


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
