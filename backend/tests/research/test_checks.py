"""Pure checks: phone matching, domain trust, lookalikes, the verdict table."""

from datetime import UTC, date, datetime

import pytest
from app.research.checks import (
    address_on_page,
    case_number_shape,
    decide_verdict,
    domain_trust,
    edition_date,
    form_number,
    form_on_page,
    lookalike,
    phone_on_page,
)
from app.research.fetch_tool import FetchedPage
from app.research.models import SignalResult

PHONE = "+18005550100"


@pytest.mark.parametrize(
    "html",
    [
        "<p>Call (800) 555-0100 today</p>",
        "<p>Call 800-555-0100</p>",
        "<p>Call 1-800-555-0100</p>",
        "<p>Call 800.555.0100</p>",
        "<p>Call 800&#8209;555&#8209;0100</p>",
        '<a href="tel:+18005550100">Call us</a>',
        '<a href="tel:1-800-555-0100">Call us</a>',
        "<p>Call <span>(800)</span> <span>555-0100</span></p>",
        "<p>Call <b>800</b>-<b>555</b>-<b>0100</b></p>",
        "<p>Call 800&nbsp;555&nbsp;0100</p>",
    ],
)
def test_phone_on_page_formats(html: str) -> None:
    assert phone_on_page(PHONE, html)


@pytest.mark.parametrize(
    "html",
    [
        "<p>Call (800) 555-0101</p>",
        "<p>No numbers here</p>",
        "<script>var n='800-555-0100'</script><p>hidden in script</p>",
    ],
)
def test_phone_not_on_page(html: str) -> None:
    assert not phone_on_page(PHONE, html)


def _page(url: str, links: list[str]) -> FetchedPage:
    return FetchedPage(
        url=url,
        final_url=url,
        status_code=200,
        html="",
        links=links,
        fetched_at=datetime.now(UTC),
    )


def test_domain_trust() -> None:
    anchor = _page("https://www.state.gov/counties", ["https://county-ss.org/contact"])
    untrusted_linker = _page("https://blog.com/", ["https://other.org/"])
    pages = [anchor, untrusted_linker]
    assert domain_trust("https://www.uscis.gov/contactcenter", pages) == "anchor"
    assert domain_trust("https://dhcs.ca.gov/x", pages) == "anchor"
    assert (
        domain_trust("https://www.county-ss.org/phones", pages) == "linked_from_anchor"
    )
    assert domain_trust("https://other.org/", pages) == "untrusted"
    assert domain_trust("https://uscis-gov.com/", pages) == "untrusted"


def test_lookalike() -> None:
    anchors = ["uscis.gov"]
    assert lookalike("https://www.uscis.gov/x", anchors) is None
    assert lookalike("dhs.gov", anchors) is None
    misread = lookalike("https://www.uscls.gov/contactcenter", anchors)
    assert misread is not None and misread.state == "uncertain"
    for fake in ("uscis-gov.com", "uscis.com", "usciss.org"):
        result = lookalike(fake, anchors)
        assert result is not None and result.state == "conflict", fake


def test_lookalike_short_names_avoid_false_hits() -> None:
    assert lookalike("ed.gov", ["hud.gov"]) is None
    assert lookalike("thehudson.com", ["hud.gov"]) is None


def _signal(name: str, state: str) -> SignalResult:
    return SignalResult(signal=name, state=state)


@pytest.mark.parametrize(
    ("states", "red_flags", "issuer_verified", "expected"),
    [
        ({"url_domains": "match", "form_id": "match"}, [], True, "verified"),
        ({"url_domains": "match", "form_id": "match"}, [], False, "unknown"),
        ({"url_domains": "match", "form_id": "not_found"}, [], True, "unknown"),
        (
            {"url_domains": "match", "form_id": "match"},
            ["gift card"],
            True,
            "suspicious",
        ),
        ({"url_domains": "conflict", "form_id": "match"}, [], True, "suspicious"),
        ({"url_domains": "uncertain", "form_id": "match"}, [], True, "unknown"),
        ({"url_domains": "uncertain", "form_id": "not_found"}, [], False, "unknown"),
        ({"issuer": "match", "form_id": "match"}, [], True, "unknown"),
    ],
)
def test_decide_verdict(states, red_flags, issuer_verified, expected) -> None:
    signals = [_signal(name, state) for name, state in states.items()]
    assert decide_verdict(signals, red_flags, issuer_verified) == expected


def test_case_number_shape() -> None:
    assert case_number_shape("3 letters + 10 digits") == (3, 10)
    assert case_number_shape("XXX##########") == (3, 10)
    assert case_number_shape("ABC1234567890") == (3, 10)
    assert case_number_shape(None) is None


def test_form_helpers() -> None:
    assert form_number("Form I-797C (Rev. 01/20/25)") == "I-797C"
    assert form_number("i797c") == "I-797C"
    assert form_on_page("I-797C", "<p>Form I-797C, Notice of Action</p>")
    assert not form_on_page("I-797C", "<p>Form I-797, Notice of Action</p>")


def test_address_on_page() -> None:
    html = "<p>Service Center, 100 Main St., Springfield, ST 00000</p>"
    assert address_on_page("100 Main Street, Springfield, ST 00000", html)
    assert not address_on_page("200 Main Street, Springfield, ST 00000", html)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("I-797C (edition 10/13/21)", date(2021, 10, 13)),
        ("Form I-797C (Rev. 01/20/2025)", date(2025, 1, 20)),
        ("I-797C", None),
        ("I-797C (edition 13/45/21)", None),
        ("I-797C (edition 01/01/2099)", None),
    ],
)
def test_edition_date(raw: str, expected: date | None) -> None:
    assert edition_date(raw, date(2026, 10, 23)) == expected
