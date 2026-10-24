"""Deterministic checks the verdict rests on. Pure functions, no I/O."""

from collections.abc import Sequence
from datetime import date
from typing import Literal

from research.fetch_tool import FetchedPage
from research.models import SignalResult, VerificationStatus

DomainTrust = Literal["anchor", "linked_from_anchor", "untrusted"]


def phone_on_page(phone: str, html: str) -> bool:
    """True if the E.164 `phone` appears in the page in any common US formatting."""
    raise NotImplementedError


def domain_trust(url: str, fetched: Sequence[FetchedPage]) -> DomainTrust:
    """Classify `url`'s domain.

    Any .gov is an anchor. A non-.gov domain is trusted only if a real
    `<a href>` on a fetched anchor page links to it.
    """
    raise NotImplementedError


def deadline_sane(deadline: date, today: date, max_days: int = 120) -> bool:
    """True if the deadline is after `today` and within `max_days`."""
    raise NotImplementedError


def decide_verdict(
    signals: Sequence[SignalResult], red_flags: Sequence[str], issuer_verified: bool
) -> VerificationStatus:
    """Any red flag or conflict -> suspicious; issuer verified and 2+ matches -> verified; else unknown."""
    raise NotImplementedError
