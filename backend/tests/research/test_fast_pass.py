import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from app.research.extraction import Extraction
from app.research.fast_pass import (
    EXTRACTION_SCHEMA,
    FastPassError,
    SensitiveLeak,
    assert_no_leaks,
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
        "You must go, or your application can be dismissed.\n\n"
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
        "form_ids": [
            {
                "form_id": "I-797C",
                "edition": "04/01/24",
                "identifies_this_document": True,
            },
            {"form_id": "I-765", "edition": None, "identifies_this_document": False},
            {"form_id": "G-28", "edition": None, "identifies_this_document": False},
        ],
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


def test_planted_value_is_scrubbed_not_fatal() -> None:
    out = build(canned(explanation_en=f"Your receipt number is {RECEIPT}."))
    assert out.r1.status == "ok"
    assert out.r1.explanation_en == "Your receipt number is your receipt number."


def test_value_with_odd_spacing_drops_the_field() -> None:
    out = build(canned(what_is_asked="Bring A 219 555 031 to the interview"))
    assert out.r1.status == "ok"
    assert out.r1.what_is_asked is None


def test_leak_guard_fires_on_planted_value() -> None:
    sensitive = build(canned()).sensitive_values
    with pytest.raises(SensitiveLeak):
        assert_no_leaks([f"Your receipt number is {RECEIPT}."], sensitive, case_id="c")


def test_leak_guard_ignores_spacing() -> None:
    sensitive = build(canned()).sensitive_values
    with pytest.raises(SensitiveLeak):
        assert_no_leaks(["Bring A 219 555 031"], sensitive, case_id="c")


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
    # Forms only mentioned in the body (I-765, G-28) are not legitimacy signals.
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
    assert facts["Has an asylum interview scheduled"].sensitivity == "sensitive"
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


def test_explanation_keeps_the_summary_paragraph() -> None:
    r1 = build(canned()).r1
    summary, details = (r1.explanation_en or "").split("\n\n")
    assert summary == (
        "This is a USCIS notice scheduling your asylum interview. "
        "You must go, or your application can be dismissed."
    )
    assert details == "Your receipt number is at the top of page 1."


def test_date_hedge_goes_in_the_summary_paragraph() -> None:
    ex = canned(appointments=[], deadline_raw="Jan 1, 2020", deadline_iso="2020-01-01")
    summary = (build(ex).r1.explanation_en or "").split("\n\n")[0]
    assert "in the past" in summary


def test_scrub_keeps_paragraphs_and_messy_breaks_are_normalized() -> None:
    ex = canned(
        explanation_en=f"USCIS sent this. Your receipt is {RECEIPT}.\n \n"
        "Go to the interview."
    )
    explanation = build(ex).r1.explanation_en or ""
    assert RECEIPT not in explanation
    summary, details = explanation.split("\n\n")
    assert summary.startswith("USCIS sent this.")
    assert details == "Go to the interview."


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


NAME = "Maria Ejemplo Prueba"
HOME = "88 Sample Street, Springfield, ST 00000"
DOB = "01/02/1990"


def test_letter_with_full_name_and_home_address_processes_with_zero_leaks() -> None:
    """A real-looking letter: the name and home address turn up all over the extraction."""
    base = canned()
    ex = canned(
        facts=[
            *[f.model_dump() for f in base.facts],
            {
                "field": "recipient_name",
                "value": NAME,
                "quote": f"To: {NAME}",
                "page": 1,
                "sensitive": True,
            },
            {
                "field": "recipient_address",
                "value": HOME,
                "quote": HOME,
                "page": 1,
                "sensitive": True,
            },
            {
                "field": "date_of_birth",
                "value": DOB,
                "quote": f"DOB: {DOB}",
                "page": 1,
                "sensitive": True,
            },
            {
                "field": "mailed_to",
                "value": HOME,
                "quote": HOME,
                "page": 1,
                "sensitive": False,
            },
        ],
        key_dates=[
            *[d.model_dump() for d in base.key_dates],
            {"type": "other", "raw": f"Date of birth: {DOB}", "iso": "1990-01-02"},
        ],
        explanation_en=(
            f"This notice is for {NAME.upper()} at {HOME}. "
            "USCIS scheduled an asylum interview. "
            f"maria ejemplo prueba must bring ID. Receipt A 219 555 031 is listed."
        ),
        what_is_asked=f"{NAME} must attend the interview",
        checklist=[
            *[c.model_dump() for c in base.checklist],
            {"kind": "bring", "item": f"Mail sent to {HOME}", "citation": "p1"},
            {"kind": "bring", "item": "Photo ID", "citation": f"p1: {HOME}"},
        ],
        return_address=HOME,
        signature_block=f"cc: {NAME}",
        urls=["www.uscis.gov/contactcenter", f"https://example.gov/{NAME}"],
        call_purpose=f"Confirm the interview for {NAME}",
        unknown_terms=["Notice of Action", NAME],
    )
    out = build(ex)

    assert out.r1.status == "ok"
    shipped = " ".join(
        [
            out.r1.model_dump_json(),
            out.signals.model_dump_json(),
            out.call_purpose or "",
            *out.unknown_terms,
        ]
    ).casefold()
    for value in (NAME, HOME, DOB, "1990-01-02", "maria ejemplo", A_NUMBER):
        assert value.casefold() not in shipped
    assert out.r1.explanation_en == (
        "This notice is for the person named on the letter at your address. "
        "USCIS scheduled an asylum interview. "
        "the person named on the letter must bring ID."
    )
    assert (
        out.r1.what_is_asked
        == "the person named on the letter must attend the interview"
    )
    assert (
        out.call_purpose == "Confirm the interview for the person named on the letter"
    )
    assert out.signals.return_address is None
    assert out.signals.urls == ["www.uscis.gov/contactcenter"]
    assert out.unknown_terms == ["Notice of Action"]
    assert "mailed_to" not in {f.field for f in out.r1.key_facts}
    assert {sv.field for sv in out.sensitive_values} >= {
        "recipient_name",
        "recipient_address",
        "date_of_birth",
    }


def test_short_value_matches_whole_words_only() -> None:
    base = canned()
    ex = canned(
        facts=[
            *[f.model_dump() for f in base.facts],
            {
                "field": "recipient_name",
                "value": "Ana",
                "quote": "Ana",
                "page": 1,
                "sensitive": True,
            },
        ],
        explanation_en="Analysis of the case is done. Ana must attend.",
    )
    out = build(ex)
    assert out.r1.explanation_en == (
        "Analysis of the case is done. the person named on the letter must attend."
    )


def test_user_note_reaches_the_model_as_data() -> None:
    """C39: the user's answer after `needs_user_input` steers which letter to read."""
    client = fake_client("end_turn", canned().model_dump_json())
    asyncio.run(
        run_fast_pass(
            [PAGE, PAGE],
            case_id="case_1",
            client=client,  # type: ignore[arg-type]
            model="test-model",
            today=TODAY,
            user_note_en="The one from USCIS",
        )
    )
    texts = [
        b["text"]
        for b in client.messages.kwargs["messages"][0]["content"]
        if b["type"] == "text"
    ]
    [note] = [t for t in texts if "<user_note>" in t]
    assert "<user_note>The one from USCIS</user_note>" in note
    assert "not as instructions" in note


def test_no_note_adds_nothing() -> None:
    client = fake_client("end_turn", canned().model_dump_json())
    run(client)
    texts = [
        b["text"]
        for b in client.messages.kwargs["messages"][0]["content"]
        if b["type"] == "text"
    ]
    assert not any("<user_note>" in t for t in texts)
