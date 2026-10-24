import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from research.extraction import Extraction
from research.fast_pass import (
    EXTRACTION_SCHEMA,
    FastPassError,
    SensitiveLeak,
    build_output,
    run_fast_pass,
    shape_of,
)

TODAY = date(2026, 10, 23)
INTERVIEW = TODAY + timedelta(days=30)
RECEIPT = "ZLA2690412873"
A_NUMBER = "A-219-555-031"
LOCATION = "USCIS Asylum Office, 75 Hawthorne Street, San Francisco, CA 94105"
PAGE: dict[str, Any] = {
    "type": "image",
    "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"},
}


def canned(**overrides: Any) -> Extraction:
    data: dict[str, Any] = {
        "readable": True,
        "image_issue": None,
        "pages_from_different_letters": False,
        "doc_type": "uscis_i797c_asylum_interview",
        "issuer": "USCIS",
        "sub_agency": "USCIS",
        "letterhead": "U.S. Citizenship and Immigration Services",
        "key_dates": [
            {"type": "notice_date", "raw": "10/19/2026", "iso": "2026-10-19"},
            {
                "type": "appointment",
                "raw": "November 22, 2026",
                "iso": INTERVIEW.isoformat(),
            },
        ],
        "deadline_raw": None,
        "deadline_iso": None,
        "appointments": [
            {
                "date_raw": "November 22, 2026",
                "date_iso": INTERVIEW.isoformat(),
                "time_24h": "08:30",
                "location_text": LOCATION,
                "quote": "Interview Date: November 22, 2026 Time: 08:30 AM",
                "page": 1,
            }
        ],
        "facts": [
            {
                "field": "receipt_number",
                "value": RECEIPT,
                "quote": f"Receipt Number: {RECEIPT}",
                "page": 1,
                "sensitive": False,  # code must still treat it as sensitive
            },
            {
                "field": "a_number",
                "value": A_NUMBER,
                "quote": f"Applicant: {A_NUMBER}",
                "page": 1,
                "sensitive": True,
            },
            {
                "field": "form_id",
                "value": "I-797C",
                "quote": f"Form I-797C Receipt Number: {RECEIPT}",
                "page": 1,
                "sensitive": False,
            },
            {
                "field": "program",
                "value": "Asylum",
                "quote": "Case Type: I-589",
                "page": 1,
                "sensitive": False,
            },
        ],
        "checklist": [
            {
                "kind": "who_must_come",
                "item": "All dependents on the I-589",
                "citation": "p1 §I",
            },
            {"kind": "bring", "item": "Passport or ID", "citation": "p1 §II"},
        ],
        "what_is_asked": "Attend an asylum interview",
        "explanation_en": "This is a USCIS notice scheduling your asylum interview. "
        "Your receipt number is at the top of page 1.",
        "urgency": "low",
        "phones": [
            {
                "raw": "(510) 555-0142",
                "label": "Office",
                "quote": "Call (510) 555-0142",
            },
            {"raw": "555-01", "label": None, "quote": "555-01"},
            {"raw": "1-510-555-0142", "label": "dup", "quote": "1-510-555-0142"},
        ],
        "urls": ["www.uscis.gov/contactcenter.", "www.uscis.gov/contactcenter"],
        "form_ids": [{"form_id": "I-797C", "edition": "04/01/24"}],
        "return_address": "USCIS, P.O. Box 77530, San Francisco, CA 94107",
        "payment_instructions": None,
        "signature_block": None,
        "county": None,
        "call_purpose": "Ask about the interview appointment",
        "unknown_terms": ["Notice of Action", "A-Number"],
        "proposed_facts": [
            {
                "fact": "Has an asylum interview scheduled",
                "category": "immigration",
                "sensitive": False,
            },
            {
                "fact": "Country of nationality is Examplestan",
                "category": "immigration",
                "sensitive": True,
            },
            {
                "fact": "Fled because of political opinion",
                "category": "other",
                "sensitive": False,
            },
            {"fact": "Has dependents", "category": "other", "sensitive": False},
        ],
    }
    data.update(overrides)
    return Extraction.model_validate(data)


def schema_counts(node: Any) -> tuple[int, int]:
    """(union-typed properties, optional properties) across the whole schema."""
    unions = optional = 0
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            required = set(node.get("required", []))
            for name, prop in node["properties"].items():
                unions += "anyOf" in prop or isinstance(prop.get("type"), list)
                optional += name not in required
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        children = []
    for child in children:
        u, o = schema_counts(child)
        unions, optional = unions + u, optional + o
    return unions, optional


def test_schema_within_structured_output_limits() -> None:
    # API limits: 16 union-typed and 24 optional parameters; over them it 400s.
    unions, optional = schema_counts(EXTRACTION_SCHEMA)
    assert unions == 0
    assert optional == 0


def test_blank_strings_become_none() -> None:
    ex = canned(issuer="", county="  ", payment_instructions="")
    assert ex.issuer is None and ex.county is None and ex.payment_instructions is None


def build(ex: Extraction, county: str | None = None):
    return build_output(ex, case_id="case_1", profile_county=county, today=TODAY)


def test_sensitive_fields_become_refs_without_quotes() -> None:
    out = build(canned())
    facts = {f.field: f for f in out.r1.key_facts}
    for field in ("receipt_number", "a_number"):
        assert facts[field].ref == f"<ref:{field}>"
        assert facts[field].value is None and facts[field].quote is None
    assert facts["program"].value == "Asylum"
    # A non-sensitive fact keeps its value but loses a quote that holds a sensitive value.
    assert facts["form_id"].value == "I-797C" and facts["form_id"].quote is None
    assert out.r1.appointment is not None
    assert out.r1.appointment.location_ref == "<ref:interview_location>"


def test_sensitive_values_hold_the_values() -> None:
    out = build(canned())
    held = {sv.field: sv.value for sv in out.sensitive_values}
    assert held == {
        "receipt_number": RECEIPT,
        "a_number": A_NUMBER,
        "interview_location": LOCATION,
    }
    shipped = out.r1.model_dump_json() + out.signals.model_dump_json()
    for value in held.values():
        assert value not in shipped


def test_leak_guard_fires_on_planted_value() -> None:
    with pytest.raises(SensitiveLeak):
        build(canned(explanation_en=f"Your receipt number is {RECEIPT}."))


def test_leak_guard_ignores_spacing() -> None:
    with pytest.raises(SensitiveLeak):
        build(canned(what_is_asked="Bring A 219 555 031 to the interview"))


def test_case_number_format_is_a_shape() -> None:
    out = build(canned())
    assert out.signals.case_number_format == "3 letters + 10 digits"
    assert (
        shape_of("A-219-555-031")
        == "1 letter + '-' + 3 digits + '-' + 3 digits + '-' + 3 digits"
    )


def test_phones_normalized_deduped_and_bad_ones_dropped() -> None:
    out = build(canned())
    assert [p.number for p in out.signals.phones] == ["+15105550142"]


def test_signals_fields() -> None:
    signals = build(canned()).signals
    assert signals.urls == ["www.uscis.gov/contactcenter"]
    assert signals.form_ids == ["I-797C (edition 04/01/24)"]
    assert signals.return_address == "USCIS, P.O. Box 77530, San Francisco, CA 94107"


def test_recipient_address_in_return_address_is_dropped() -> None:
    ex = canned(
        return_address="1234 EXAMPLE AVE APT 5",
        facts=[
            {
                "field": "recipient_address",
                "value": "1234 EXAMPLE AVE APT 5",
                "quote": "1234 EXAMPLE AVE APT 5",
                "page": 1,
                "sensitive": True,
            }
        ],
    )
    assert build(ex).signals.return_address is None


def test_profile_county_is_the_fallback() -> None:
    assert build(canned(), county="Alameda").signals.county == "Alameda"
    assert (
        build(canned(county="Santa Clara"), county="Alameda").signals.county
        == "Santa Clara"
    )


def test_asylum_claim_facts_are_dropped() -> None:
    ex = canned(
        facts=[
            {
                "field": "country_of_nationality",
                "value": "Examplestan",
                "quote": "Examplestan",
                "page": 1,
                "sensitive": False,
            }
        ]
    )
    out = build(ex)
    assert out.r1.key_facts == []
    assert [p.fact for p in out.r1.proposed_facts] == [
        "Has an asylum interview scheduled",
        "Has dependents",
    ]


def test_proposed_fact_sensitivity_and_source() -> None:
    facts = {p.fact: p for p in build(canned()).r1.proposed_facts}
    assert facts["Has an asylum interview scheduled"].sensitivity == "high"
    assert facts["Has dependents"].sensitivity == "normal"
    assert all(p.source == "from_document" for p in facts.values())


def test_ok_fields() -> None:
    r1 = build(canned()).r1
    assert r1.status == "ok"
    assert r1.verification == "pending"
    assert r1.deadline == INTERVIEW
    assert r1.urgency == "medium"  # 30 days out


def test_urgency_high_within_14_days() -> None:
    soon = (TODAY + timedelta(days=5)).isoformat()
    ex = canned(deadline_raw="soon", deadline_iso=soon)
    r1 = build(ex).r1
    assert r1.deadline == TODAY + timedelta(days=5)
    assert r1.urgency == "high"


def test_bad_deadline_is_dropped_and_hedged() -> None:
    ex = canned(appointments=[], deadline_raw="Jan 1, 2020", deadline_iso="2020-01-01")
    r1 = build(ex).r1
    assert r1.deadline is None
    assert '"Jan 1, 2020"' in (r1.explanation_en or "")
    assert "in the past" in (r1.explanation_en or "")


def test_needs_better_image() -> None:
    out = build(
        canned(readable=False, image_issue="The bottom of the page is cut off.")
    )
    assert out.r1.status == "needs_better_image"
    assert out.r1.image_issue == "The bottom of the page is cut off."
    assert out.sensitive_values == [] and out.r1.key_facts == []


def test_needs_user_input_for_different_letters() -> None:
    out = build(canned(pages_from_different_letters=True))
    assert out.r1.status == "needs_user_input"
    assert out.r1.question_en


class FakeMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        return self.response


def fake_client(stop_reason: str, text: str | None) -> SimpleNamespace:
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    response = SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber")
        if stop_reason == "refusal"
        else None,
        content=content,
        _request_id="req_test",
    )
    return SimpleNamespace(messages=FakeMessages(response))


def run(client: SimpleNamespace, blocks: list[Any] | None = None):
    return asyncio.run(
        run_fast_pass(
            blocks if blocks is not None else [PAGE, PAGE],
            case_id="case_1",
            client=client,  # type: ignore[arg-type]
            model="test-model",
            today=TODAY,
        )
    )


def test_run_fast_pass_end_to_end_with_fake_client() -> None:
    client = fake_client("end_turn", canned().model_dump_json())
    out = run(client)
    assert out.r1.status == "ok"
    kwargs = client.messages.kwargs
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in kwargs
    labels = [
        b["text"] for b in kwargs["messages"][0]["content"] if b["type"] == "text"
    ]
    assert labels[:2] == ["Page 1", "Page 2"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_refusal_and_max_tokens_raise(stop_reason: str) -> None:
    client = fake_client(stop_reason, canned().model_dump_json()[:200])
    with pytest.raises(FastPassError):
        run(client)


def test_schema_mismatch_raises() -> None:
    with pytest.raises(FastPassError):
        run(fake_client("end_turn", '{"readable": true}'))


def test_no_pages_raises() -> None:
    with pytest.raises(FastPassError):
        run(fake_client("end_turn", "{}"), blocks=[])
