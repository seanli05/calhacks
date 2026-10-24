"""The rehearsal harness only ever touches a test branch."""

import pytest
from app.dev.rehearsal import ScriptedLlm, use_test_branch
from app.phone.menu import MenuDecision, PressAction
from app.phone.phase import PhaseJudgment
from app.settings import get_settings

SHARED = "postgresql://u:p@ep-shared.us-east-2.aws.neon.tech/db?sslmode=require"
TEST = "postgresql://u:p@ep-test.us-east-2.aws.neon.tech/db?sslmode=require"


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", SHARED)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_refuses_the_shared_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", SHARED)
    with pytest.raises(SystemExit, match="shared database"):
        use_test_branch()


def test_refuses_without_a_test_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "")
    with pytest.raises(SystemExit, match="TEST_DATABASE_URL"):
        use_test_branch()


def test_points_every_helper_at_the_test_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", TEST)
    use_test_branch()
    assert "ep-test" in get_settings().async_database_url


async def test_scripted_model_answers_both_questions() -> None:
    llm = ScriptedLlm()
    judgment = await llm.parse(
        system="",
        user='NOW HEARD:\n"Please hold."',
        output_type=PhaseJudgment,
        timeout_s=1,
    )
    assert judgment.phase == "hold"
    decision = await llm.parse(
        system="",
        user='NOW HEARD:\n"For English, press 1."',
        output_type=MenuDecision,
        timeout_s=1,
    )
    assert isinstance(decision.action, PressAction)
