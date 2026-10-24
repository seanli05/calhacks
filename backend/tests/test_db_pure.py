"""DB-layer tests that need no database."""

import re

import pytest
from app.db import reset
from app.db.ids import new_id


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
