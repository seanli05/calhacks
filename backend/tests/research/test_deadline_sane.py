from datetime import date

from app.research.checks import deadline_sane
from app.research.fast_pass import check_date

TODAY = date(2026, 10, 23)


def test_valid() -> None:
    assert deadline_sane(date(2026, 11, 18), TODAY)
    assert deadline_sane(TODAY, TODAY)
    assert check_date("2026-11-18", TODAY, 120) == (date(2026, 11, 18), None)


def test_past() -> None:
    assert not deadline_sane(date(2026, 10, 22), TODAY)
    assert check_date("2026-10-22", TODAY, 120) == (None, "in_the_past")


def test_far_future() -> None:
    assert not deadline_sane(date(2027, 3, 1), TODAY)
    assert deadline_sane(date(2027, 3, 1), TODAY, max_days=365)
    assert check_date("2027-12-01", TODAY, 365) == (None, "too_far")


def test_unparseable() -> None:
    for value in (None, "", "next Tuesday", "2026-13-01"):
        assert check_date(value, TODAY, 120) == (None, "unparseable")
