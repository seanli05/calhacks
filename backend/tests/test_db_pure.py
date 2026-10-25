"""DB-layer tests that need no database."""

import re

import pytest
from app.contracts import CallState, FastResult, JobStatus, VerificationStatus
from app.db import reset
from app.db.ids import new_id
from app.db.progress import CaseStage, compute_stage


def test_new_id_format() -> None:
    assert re.fullmatch(r"case_[0-9a-f]{16}", new_id("case"))
    assert new_id("case") != new_id("case")


def test_reset_flags() -> None:
    args = reset.parse_args(["--yes", "--empty"])
    assert args.yes and args.empty
    args = reset.parse_args([])
    assert not args.yes and not args.empty


def test_reset_refuses_without_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def must_not_run(empty: bool) -> None:
        raise AssertionError("reset ran without --yes")

    monkeypatch.setattr(reset, "reset", must_not_run)
    assert reset.main([]) == 2
    assert reset.main(["--empty"]) == 2


def test_seed_fast_result_is_a_valid_r1() -> None:
    assert FastResult.model_validate(reset.demo_fast_result("case_x")).status == "ok"


def _stage(**overrides: object) -> CaseStage:
    inputs: dict[str, object] = {
        "closed": False,
        "latest_call_state": None,
        "latest_verification": None,
        "fast_job": None,
        "deep_job": None,
        "fast_result": None,
    }
    return compute_stage(**{**inputs, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, CaseStage.RECEIVED),
        ({"fast_job": JobStatus.QUEUED}, CaseStage.EXPLAINING),
        ({"fast_job": JobStatus.RUNNING}, CaseStage.EXPLAINING),
        ({"fast_result": "needs_better_image"}, CaseStage.NEEDS_BETTER_IMAGE),
        (
            {"fast_job": JobStatus.QUEUED, "fast_result": "needs_better_image"},
            CaseStage.EXPLAINING,
        ),
        ({"fast_result": "needs_user_input"}, CaseStage.NEEDS_ANSWER),
        (
            {"fast_job": JobStatus.QUEUED, "fast_result": "needs_user_input"},
            CaseStage.EXPLAINING,
        ),
        ({"fast_job": JobStatus.DONE, "fast_result": "ok"}, CaseStage.CHECKING),
        ({"deep_job": JobStatus.RUNNING}, CaseStage.CHECKING),
        ({"latest_verification": "pending"}, CaseStage.CHECKING),
        ({"latest_verification": "suspicious"}, CaseStage.SUSPICIOUS),
        ({"latest_verification": "unknown"}, CaseStage.UNKNOWN),
        ({"latest_verification": "verified"}, CaseStage.VERIFIED),
        (
            {"latest_verification": "verified", "call_offered": True},
            CaseStage.AWAITING_CONSENT,
        ),
        ({"latest_verification": "unknown", "call_offered": True}, CaseStage.UNKNOWN),
        ({"latest_call_state": "dialing"}, CaseStage.CALLING),
        ({"latest_call_state": "menu"}, CaseStage.CALLING),
        ({"latest_call_state": "hold"}, CaseStage.ON_HOLD),
        ({"latest_call_state": "human_detected"}, CaseStage.CONNECTED),
        ({"latest_call_state": "connected"}, CaseStage.CONNECTED),
        ({"latest_call_state": "wrap_up"}, CaseStage.CALL_ENDED),
        ({"latest_call_state": "ended"}, CaseStage.CALL_ENDED),
        ({"closed": True, "latest_call_state": "hold"}, CaseStage.CLOSED),
    ],
)
def test_compute_stage(overrides: dict[str, object], expected: CaseStage) -> None:
    assert _stage(**overrides) == expected


def test_every_call_state_has_a_stage() -> None:
    for state in CallState:
        _stage(latest_call_state=state)


def test_call_outranks_verdict() -> None:
    stage = _stage(
        latest_verification=VerificationStatus.VERIFIED,
        latest_call_state=CallState.HOLD,
        fast_result="ok",
    )
    assert stage == CaseStage.ON_HOLD


def test_demo_users_keep_an_account_or_make_one() -> None:
    from app.db import reset

    assert reset.parse_demo_user("user_abc=mariam") == reset.DemoUser(
        "mariam", user_id="user_abc"
    )
    assert reset.parse_demo_user("+15105550100=ana") == reset.DemoUser(
        "ana", number="+15105550100"
    )
    for bad in ("user_abc=bob", "abc=ana", "user_abc"):
        with pytest.raises(ValueError):
            reset.parse_demo_user(bad)
