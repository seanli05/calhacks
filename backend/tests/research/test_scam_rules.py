"""Scam red flags: deterministic, offline."""

import pytest
from app.research.hints import where_to_look
from app.research.models import LegitimacySignals
from app.research.scam_rules import scam_red_flags

USCIS = where_to_look("uscis_i797c")


def _flags(**fields) -> list[str]:
    fields.setdefault("case_number_format", "3 letters + 10 digits")
    return scam_red_flags(LegitimacySignals(**fields), USCIS)


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("Pay with Google Play gift cards", "gift card"),
        ("Send the fee by Western Union", "Western Union"),
        ("Complete a wire transfer today", "wire transfer"),
        ("Pay in Bitcoin to this wallet", "cryptocurrency"),
        ("Send payment via Zelle", "Zelle"),
    ],
)
def test_payment_methods(text: str, needle: str) -> None:
    flags = _flags(payment_instructions=text)
    assert any(needle in f and "USCIS never" in f for f in flags)


def test_threat() -> None:
    flags = _flags(payment_instructions="Pay now or you will be arrested and deported")
    assert any("arrest or deportation" in f for f in flags)


def test_notario() -> None:
    flags = _flags(signature_block="Maria Lopez, Notario Publico")
    assert any("notario" in f for f in flags)


def test_non_gov_link_on_federal_notice() -> None:
    flags = _flags(urls=["https://uscis-help.com/pay", "https://www.uscis.gov/x"])
    assert any("uscis-help.com" in f and ".gov" in f for f in flags)


def test_non_gov_link_ok_on_non_federal_letter() -> None:
    signals = LegitimacySignals(urls=["https://county-ss.org/renew"])
    assert scam_red_flags(signals, where_to_look("county_benefits")) == []


def test_urgency_without_case_number() -> None:
    flags = scam_red_flags(
        LegitimacySignals(payment_instructions="FINAL NOTICE: act now"), USCIS
    )
    assert any("no case or receipt number" in f for f in flags)
    assert not any(
        "no case or receipt number" in f
        for f in _flags(payment_instructions="FINAL NOTICE")
    )


def test_ssn_by_phone() -> None:
    flags = _flags(payment_instructions="Call us and give your Social Security number")
    assert any("Social Security" in f for f in flags)


def test_legit_notice_has_no_flags() -> None:
    assert (
        _flags(
            letterhead="U.S. Citizenship and Immigration Services",
            urls=["https://www.uscis.gov/contactcenter"],
            form_ids=["I-797C"],
            signature_block="Application for Asylum and for Withholding of Removal",
        )
        == []
    )
