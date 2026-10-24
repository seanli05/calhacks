"""Deep pass with a scripted fake client and a replayed synthetic web. No network."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from research.deep_pass import run_deep_pass
from research.fetch_tool import replay_resolver, replay_transport, save_fixture
from research.models import LegitimacySignals
from research.verify_cache import VerifyCache, seed_entry

SIGNALS_DIR = Path("fixtures/signals")
CONTACT = "https://www.uscis.gov/contactcenter"
FORM_PAGE = "https://www.uscis.gov/i-797c"
LOOKALIKE = "https://www.uscis-help.com/phones"

CONTACT_HTML = """<html><body>
  <header>U.S. Citizenship and Immigration Services</header>
  <h1>Contact Center</h1>
  <p>Questions about your case or appointment? Call <a href="tel:+18005550100">800-555-0100</a>.</p>
</body></html>"""
FORM_HTML = f"""<html><body>
  <p>U.S. Citizenship and Immigration Services</p>
  <h1>Form I-797C, Notice of Action</h1>
  <p>Form I-589, Application for Asylum. Questions? <a href="{CONTACT}">Contact us</a>.</p>
</body></html>"""
LOOKALIKE_HTML = "<p>USCIS help line: (877) 555-0199</p>"


def load_signals(name: str) -> tuple[LegitimacySignals, str | None, str | None]:
    raw = json.loads((SIGNALS_DIR / name).read_text())
    return (
        LegitimacySignals.model_validate(raw["signals"]),
        raw.get("call_purpose"),
        raw.get("doc_type"),
    )


def block(type_: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=type_, **fields)


def turn(stop_reason: str, *blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop_reason, stop_details=None
    )


def search(query: str) -> list[SimpleNamespace]:
    return [
        block("server_tool_use", id="srv_1", name="web_search", input={"query": query}),
        block("web_search_tool_result", tool_use_id="srv_1", content=[]),
    ]


def fetch(id_: str, url: str) -> SimpleNamespace:
    return block("tool_use", id=id_, name="fetch_page", input={"url": url})


def submit(phone: str | None, source: str | None, **extra: Any) -> SimpleNamespace:
    payload = {
        "issuer_official_domain": "uscis.gov",
        "official_phone": phone,
        "phone_source_url": source,
        "phone_label": "USCIS Contact Center",
        "phone_purpose": "Questions about an existing case or appointment",
        "alternative_contacts": [],
        "evidence": [],
        "notes": "",
        **extra,
    }
    return block("tool_use", id="submit_1", name="submit_findings", input=payload)


class FakeClient:
    """Plays scripted turns; records the messages sent on every call."""

    def __init__(self, turns: list[SimpleNamespace]) -> None:
        self._turns = list(turns)
        self.calls: list[list[dict[str, Any]]] = []
        self.beta = SimpleNamespace(messages=self)

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(list(kwargs["messages"]))
        if not self._turns:
            raise AssertionError("unexpected model call")
        return self._turns.pop(0)


def good_turns(
    phone: str = "800-555-0100", source: str = CONTACT
) -> list[SimpleNamespace]:
    return [
        turn(
            "tool_use",
            *search("USCIS Contact Center phone number"),
            fetch("f1", FORM_PAGE),
            fetch("f2", CONTACT),
        ),
        turn("tool_use", submit(phone, source)),
    ]


@pytest.fixture
def web(tmp_path: Path) -> Path:
    directory = tmp_path / "web"
    save_fixture(directory, CONTACT, CONTACT_HTML)
    save_fixture(directory, FORM_PAGE, FORM_HTML)
    save_fixture(directory, LOOKALIKE, LOOKALIKE_HTML)
    return directory


class Log:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def __call__(self, event: str, summary: str, data: dict[str, Any]) -> None:
        self.events.append((event, summary, data))


async def run(
    signals_file: str,
    client: FakeClient,
    web_dir: Path,
    *,
    cache: VerifyCache | None = None,
    seed: VerifyCache | None = None,
    log: Log | None = None,
    signals_update: dict[str, Any] | None = None,
):
    signals, purpose, doc_type = load_signals(signals_file)
    signals = signals.model_copy(update=signals_update or {})
    async with httpx.AsyncClient(transport=replay_transport(web_dir)) as http:
        return await run_deep_pass(
            signals,
            purpose,
            None,
            client=client,
            model="test-model",
            http=http,
            log=log,
            doc_type=doc_type,
            cache=cache,
            seed=seed,
            resolve=replay_resolver,
        )


@pytest.mark.asyncio
async def test_good_path_verified_with_trust_chain(web: Path) -> None:
    findings = await run("uscis_interview.json", FakeClient(good_turns()), web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+18005550100"
    assert v.letter_phone_matches is None
    assert findings.trust_chain == [FORM_PAGE, CONTACT]
    states = {s.signal: s.state for s in v.signals}
    assert states["issuer"] == "match"
    assert states["form_id"] == "match"
    assert states["url_domains"] == "match"
    assert states["case_number_format"] == "match"
    assert states["letter_phone"] == "not_found"


@pytest.mark.asyncio
async def test_number_not_on_page_is_rejected(web: Path) -> None:
    findings = await run(
        "uscis_interview.json", FakeClient(good_turns(phone="800-555-0111")), web
    )
    assert findings.verification.official_phone is None
    assert all(c.phone != "+18005550111" for c in findings.alternative_contacts)
    assert any("does not appear" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_number_on_untrusted_domain_is_rejected(web: Path) -> None:
    turns = [
        turn("tool_use", fetch("f1", LOOKALIKE)),
        turn("tool_use", submit("(877) 555-0199", LOOKALIKE)),
    ]
    findings = await run("uscis_interview.json", FakeClient(turns), web)
    assert findings.verification.official_phone is None
    assert findings.trust_chain == []
    assert any("not a trusted domain" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_snippet_only_number_is_rejected(web: Path) -> None:
    turns = [
        turn("tool_use", *search("USCIS phone")),
        turn("tool_use", submit("800-555-0100", CONTACT)),
    ]
    findings = await run("uscis_interview.json", FakeClient(turns), web)
    assert findings.verification.official_phone is None
    assert any("not fetched" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_pause_turn_is_resent_without_new_user_message(web: Path) -> None:
    paused = turn("pause_turn", *search("USCIS Contact Center"))
    client = FakeClient([paused, *good_turns()])
    findings = await run("uscis_interview.json", client, web)
    assert findings.verification.official_phone == "+18005550100"
    assert len(client.calls) == 3
    resumed = client.calls[1]
    assert resumed[-1]["role"] == "assistant"
    assert resumed[-1]["content"] == paused.content


@pytest.mark.asyncio
async def test_log_events_emitted(web: Path) -> None:
    log = Log()
    await run("uscis_interview.json", FakeClient(good_turns()), web, log=log)
    kinds = [event for event, _, _ in log.events]
    assert ("research.search", "Searched: USCIS Contact Center phone number") in [
        (e, s) for e, s, _ in log.events
    ]
    assert kinds.count("research.fetch") == 2
    assert "research.check" in kinds
    assert any(d.get("check") == "verdict" for e, _, d in log.events)


@pytest.mark.asyncio
async def test_scam_is_suspicious_without_web_calls(tmp_path: Path) -> None:
    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected fetch {request.url}")

    signals, purpose, doc_type = load_signals("scam_uscis.json")
    client = FakeClient([])
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as http:
        findings = await run_deep_pass(
            signals,
            purpose,
            None,
            client=client,
            model="m",
            http=http,
            doc_type=doc_type,
        )
    v = findings.verification
    assert v.status == "suspicious"
    assert client.calls == []
    assert v.official_phone is None
    assert any("gift card" in f for f in v.red_flags)
    assert any("arrest or deportation" in f for f in v.red_flags)
    assert all(c.phone != "+12025550147" for c in findings.alternative_contacts)


@pytest.mark.asyncio
async def test_misread_domain_is_uncertain_not_suspicious(web: Path) -> None:
    findings = await run("lookalike_misread.json", FakeClient(good_turns()), web)
    v = findings.verification
    assert v.status != "suspicious"
    assert {s.signal: s.state for s in v.signals}["url_domains"] == "uncertain"
    assert v.red_flags == []


@pytest.mark.asyncio
async def test_refusal_stops_discovery(web: Path) -> None:
    refused = SimpleNamespace(
        content=[],
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber"),
    )
    findings = await run("uscis_interview.json", FakeClient([refused]), web)
    assert findings.verification.official_phone is None
    assert any("declined" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_cache_fallback_rechecks_snapshot(web: Path, tmp_path: Path) -> None:
    cache = VerifyCache(tmp_path / "cache")
    await run("uscis_interview.json", FakeClient(good_turns()), web, cache=cache)

    # Live run fails: the contact page can no longer be fetched.
    empty_web = tmp_path / "empty"
    empty_web.mkdir()
    findings = await run(
        "uscis_interview.json", FakeClient(good_turns()), empty_web, cache=cache
    )
    v = findings.verification
    assert v.official_phone == "+18005550100"
    assert v.evidence[0].startswith("Verified from uscis.gov on ")

    # A snapshot that no longer shows the number is never used.
    entry = cache.load("uscis.gov", "case_questions")
    for page in entry.pages:
        page.html = page.html.replace("800-555-0100", "").replace(
            "tel:+18005550100", ""
        )
    cache.save(entry)
    findings = await run(
        "uscis_interview.json", FakeClient(good_turns()), empty_web, cache=cache
    )
    assert findings.verification.official_phone is None
    assert all(c.phone is None for c in findings.alternative_contacts)


DIRECTORY = "https://www.directory.gov/agencies/uscis"
DIRECTORY_HTML = """<p>U.S. Citizenship and Immigration Services</p>
<p>Main line: 800-555-0100. TTY: 800-555-0177.</p>"""


@pytest.fixture
def blocked_web(tmp_path: Path) -> Path:
    """The issuer's site answers with a bot wall; another .gov lists its numbers."""
    directory = tmp_path / "blocked"
    for url in (CONTACT, FORM_PAGE, "https://www.uscis.gov/about-us"):
        save_fixture(directory, url, "<p>Access Denied</p>", status_code=403)
    save_fixture(directory, DIRECTORY, DIRECTORY_HTML)
    return directory


@pytest.mark.asyncio
async def test_blocked_issuer_is_reported_and_not_substituted(
    blocked_web: Path,
) -> None:
    log = Log()
    turns = [
        turn(
            "tool_use",
            fetch("f1", CONTACT),
            fetch("f2", FORM_PAGE),
            fetch("f3", "https://www.uscis.gov/about-us"),
            fetch("f4", DIRECTORY),
        ),
        turn(
            "tool_use",
            submit(
                "800-555-0100",
                DIRECTORY,
                alternative_contacts=[
                    {
                        "name": "USCIS TTY",
                        "purpose": "TTY line",
                        "phone": "800-555-0177",
                        "source_url": DIRECTORY,
                    }
                ],
                notes="Snippet says call 800-555-0100; bring your own interpreter.",
            ),
        ),
    ]
    findings = await run(
        "uscis_interview.json", FakeClient(turns), blocked_web, log=log
    )
    v = findings.verification
    assert v.official_phone is None
    assert all(c.phone is None for c in findings.alternative_contacts)
    assert any("uscis.gov blocked our automated fetch" in e for e in v.evidence)
    assert not any("Snippet" in e or "interpreter" in e for e in v.evidence)
    assert {s.signal: s.state for s in v.signals}["issuer"] == "not_found"
    # Two bot walls, then the third uscis.gov fetch is skipped.
    fetched = [d.get("final_url") for e, _, d in log.events if e == "research.fetch"]
    assert fetched == [CONTACT, FORM_PAGE, DIRECTORY]


@pytest.mark.asyncio
async def test_alternative_phone_kept_only_on_issuer_domain(web: Path) -> None:
    tty_contact = CONTACT_HTML.replace("</body>", "<p>TTY: 800-555-0177</p></body>")
    save_fixture(web, CONTACT, tty_contact)
    turns = good_turns()
    turns[-1] = turn(
        "tool_use",
        submit(
            "800-555-0100",
            CONTACT,
            alternative_contacts=[
                {
                    "name": "USCIS TTY",
                    "purpose": "TTY line",
                    "phone": "800-555-0177",
                    "source_url": CONTACT,
                }
            ],
        ),
    )
    findings = await run("uscis_interview.json", FakeClient(turns), web)
    assert findings.verification.status == "verified"
    assert [c.phone for c in findings.alternative_contacts] == ["+18005550177"]


@pytest.mark.asyncio
async def test_repeated_search_block_logged_once(web: Path) -> None:
    log = Log()
    first = search("USCIS Contact Center")
    turns = [
        turn("pause_turn", *first),
        turn("tool_use", *first, fetch("f1", FORM_PAGE), fetch("f2", CONTACT)),
        turn("tool_use", submit("800-555-0100", CONTACT)),
    ]
    await run("uscis_interview.json", FakeClient(turns), web, log=log)
    assert [e for e, _, _ in log.events].count("research.search") == 1


USA_GOV = "https://www.usa.gov/agencies/u-s-citizenship-and-immigration-services"
USA_GOV_HTML = """<h1>U.S. Citizenship and Immigration Services</h1>
<p>Main phone number: 1-800-555-0100</p><p>TTY: 1-800-555-0177</p>
<p>Website: <a href="http://www.uscis.gov">uscis.gov</a></p>"""
OTHER_AGENCY = "https://www.usa.gov/agencies/some-other-agency"
OTHER_AGENCY_HTML = """<h1>Some Other Agency</h1><p>Part of the Department of Homeland
Security. Main phone number: 1-800-555-0188</p><a href="https://www.other.gov">other.gov</a>"""


@pytest.fixture
def directory_web(blocked_web: Path) -> Path:
    save_fixture(blocked_web, USA_GOV, USA_GOV_HTML)
    save_fixture(blocked_web, OTHER_AGENCY, OTHER_AGENCY_HTML)
    return blocked_web


def directory_turns(phone: str, source: str, **extra: Any) -> list[SimpleNamespace]:
    return [
        turn("tool_use", fetch("f1", CONTACT), fetch("f2", FORM_PAGE)),
        turn("tool_use", fetch("f3", source)),
        turn("tool_use", submit(phone, source, **extra)),
    ]


@pytest.mark.asyncio
async def test_directory_used_when_issuer_site_blocked(directory_web: Path) -> None:
    turns = directory_turns(
        "1-800-555-0100",
        USA_GOV,
        alternative_contacts=[
            {
                "name": "USCIS TTY",
                "purpose": "TTY line",
                "phone": "1-800-555-0177",
                "source_url": USA_GOV,
            }
        ],
    )
    findings = await run("uscis_interview.json", FakeClient(turns), directory_web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+18005550100"
    assert findings.trust_chain == [USA_GOV]
    assert any("usa.gov federal directory" in e for e in v.evidence)
    assert any("uscis.gov blocked" in e for e in v.evidence)
    assert {s.signal: s.state for s in v.signals}["issuer"] == "match"
    assert [c.phone for c in findings.alternative_contacts] == ["+18005550177"]


@pytest.mark.asyncio
async def test_directory_not_used_when_issuer_site_reachable(web: Path) -> None:
    save_fixture(web, USA_GOV, USA_GOV_HTML)
    turns = [
        turn("tool_use", fetch("f1", CONTACT), fetch("f2", USA_GOV)),
        turn("tool_use", submit("1-800-555-0100", USA_GOV)),
    ]
    findings = await run("uscis_interview.json", FakeClient(turns), web)
    assert findings.verification.official_phone is None
    assert any("not the issuer's domain" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_directory_page_for_another_agency_rejected(directory_web: Path) -> None:
    turns = directory_turns("1-800-555-0188", OTHER_AGENCY)
    findings = await run("uscis_interview.json", FakeClient(turns), directory_web)
    v = findings.verification
    assert v.official_phone is None
    assert all(c.phone is None for c in findings.alternative_contacts)
    assert {s.signal: s.state for s in v.signals}["issuer"] == "not_found"


@pytest.mark.asyncio
async def test_special_purpose_line_not_accepted_as_main(directory_web: Path) -> None:
    turns = directory_turns("1-800-555-0177", USA_GOV, phone_label="TTY")
    findings = await run("uscis_interview.json", FakeClient(turns), directory_web)
    assert findings.verification.official_phone is None
    assert any("special-purpose line" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_directory_result_cached_under_issuer(
    directory_web: Path, tmp_path: Path
) -> None:
    cache = VerifyCache(tmp_path / "cache")
    await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        directory_web,
        cache=cache,
    )
    assert cache.load("uscis.gov", "case_questions") is not None
    empty_web = tmp_path / "empty"
    empty_web.mkdir()
    findings = await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        empty_web,
        cache=cache,
    )
    assert findings.verification.official_phone == "+18005550100"
    assert findings.verification.evidence[0].startswith("Verified from usa.gov on ")


SEED_HTML = """<h1>U.S. Citizenship and Immigration Services</h1>
<p>Contact Center: 800-555-0100</p>
<p>Form I-589, Application for Asylum and for Withholding of Removal</p>"""
# Redacted copy: no case number, no form edition, so only a fetched page can match form_id.
REDACTED = {"case_number_format": None, "form_ids": ["I-797C", "I-589"]}


def seeded(tmp_path: Path, html: str = SEED_HTML) -> VerifyCache:
    seed = VerifyCache(tmp_path / "seed")
    seed.save(
        seed_entry(
            html,
            CONTACT,
            "800-555-0100",
            datetime(2026, 10, 20, tzinfo=UTC),
            "case_questions",
        )
    )
    return seed


@pytest.mark.asyncio
async def test_seed_snapshot_checked_when_issuer_blocked(
    directory_web: Path, tmp_path: Path
) -> None:
    turns = directory_turns("1-800-555-0100", USA_GOV)
    without = await run(
        "uscis_interview.json",
        FakeClient(turns),
        directory_web,
        signals_update=REDACTED,
    )
    assert without.verification.status == "unknown"

    log = Log()
    findings = await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        directory_web,
        seed=seeded(tmp_path),
        log=log,
        signals_update=REDACTED,
    )
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+18005550100"
    assert {s.signal: s.state for s in v.signals}["form_id"] == "match"
    # The number came from usa.gov; the snapshot only supplied the form match.
    assert v.evidence[0] == (
        "Checked against the uscis.gov snapshot from 2026-10-20 "
        "(the live uscis.gov site could not be fetched)"
    )
    assert any(d.get("check") == "seed_snapshot" for _, _, d in log.events)


@pytest.mark.asyncio
async def test_seed_snapshot_ignored_when_issuer_reachable(
    web: Path, tmp_path: Path
) -> None:
    findings = await run(
        "uscis_interview.json",
        FakeClient(good_turns()),
        web,
        seed=seeded(tmp_path),
    )
    assert not any("snapshot" in e for e in findings.verification.evidence)


def test_seed_entry_refuses_page_without_the_number() -> None:
    with pytest.raises(ValueError):
        seed_entry(
            "<p>U.S. Citizenship and Immigration Services</p>",
            CONTACT,
            "800-555-0100",
            datetime(2026, 10, 20, tzinfo=UTC),
            "case_questions",
        )


@pytest.mark.asyncio
async def test_number_verified_from_snapshot_replaces_bot_wall(
    blocked_web: Path, tmp_path: Path
) -> None:
    # The stub was fetched as www.uscis.gov/contactcenter; the seed is saved without www.
    seed = VerifyCache(tmp_path / "seed")
    seed.save(
        seed_entry(
            SEED_HTML,
            "https://uscis.gov/contactcenter/",
            "800-555-0100",
            datetime(2026, 10, 20, tzinfo=UTC),
            "case_questions",
        )
    )
    turns = [
        turn("tool_use", fetch("f1", CONTACT)),
        turn("tool_use", submit("800-555-0100", CONTACT)),
    ]
    findings = await run(
        "uscis_interview.json", FakeClient(turns), blocked_web, seed=seed
    )
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+18005550100"
    assert v.evidence[0].startswith("Verified from uscis.gov snapshot on 2026-10-20")


@pytest.mark.asyncio
async def test_seed_used_when_no_number_was_submitted(
    blocked_web: Path, tmp_path: Path
) -> None:
    turns = [
        turn("tool_use", fetch("f1", CONTACT)),
        SimpleNamespace(
            content=[],
            stop_reason="refusal",
            stop_details=SimpleNamespace(category="cyber"),
        ),
    ]
    findings = await run(
        "uscis_interview.json", FakeClient(turns), blocked_web, seed=seeded(tmp_path)
    )
    v = findings.verification
    assert v.official_phone == "+18005550100"
    assert v.evidence[0].startswith("Verified from uscis.gov on 2026-10-20")


COUNTY_CONTACT = "https://www.examplecounty.gov/social-services/contact"
COUNTY_HTML = """<h1>County of Example, Department of Social Services</h1>
<p>100 Main Street, Springfield, ST 00000</p>
<p>Customer service: (202) 555-0123</p>"""


@pytest.mark.asyncio
async def test_seed_applies_to_county_letters_without_fixed_domain(
    tmp_path: Path,
) -> None:
    """County hints have no issuer_domains; the seed is found via the submitted domain."""
    web_dir = tmp_path / "county_web"
    save_fixture(web_dir, COUNTY_CONTACT, "<p>Access Denied</p>", status_code=403)
    seed = VerifyCache(tmp_path / "seed")
    seed.save(
        seed_entry(
            COUNTY_HTML,
            COUNTY_CONTACT,
            "(202) 555-0123",
            datetime(2026, 10, 20, tzinfo=UTC),
            "renewal",
        )
    )

    def turns() -> list[SimpleNamespace]:
        return [
            turn("tool_use", fetch("f1", COUNTY_CONTACT)),
            turn(
                "tool_use",
                submit(
                    "(202) 555-0123",
                    COUNTY_CONTACT,
                    issuer_official_domain="examplecounty.gov",
                    phone_label="Customer service",
                    phone_purpose="Benefits renewal questions",
                ),
            ),
        ]

    without = await run("county_renewal.json", FakeClient(turns()), web_dir)
    assert without.verification.official_phone is None

    findings = await run("county_renewal.json", FakeClient(turns()), web_dir, seed=seed)
    v = findings.verification
    assert v.official_phone == "+12025550123"
    assert v.status == "verified"
    assert v.evidence[0].startswith(
        "Verified from examplecounty.gov snapshot on 2026-10-20"
    )


@pytest.mark.asyncio
async def test_seed_never_rescues_a_scam(tmp_path: Path) -> None:
    signals, purpose, doc_type = load_signals("scam_uscis.json")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))
    ) as http:
        findings = await run_deep_pass(
            signals,
            purpose,
            None,
            client=FakeClient([]),
            model="m",
            http=http,
            doc_type=doc_type,
            seed=seeded(tmp_path),
        )
    v = findings.verification
    assert v.status == "suspicious"
    assert v.official_phone is None
    assert not any("snapshot" in e for e in v.evidence)


@pytest.mark.asyncio
async def test_known_form_with_edition_matches_from_config(
    directory_web: Path,
) -> None:
    findings = await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        directory_web,
        signals_update={
            "case_number_format": None,
            "form_ids": ["I-797C (edition 10/13/21)", "I-765", "G-28"],
        },
    )
    form = next(s for s in findings.verification.signals if s.signal == "form_id")
    assert form.state == "match"
    assert form.evidence == [
        "I-797C (edition 2021-10-13): known USCIS form (config)",
        "I-765 ignored: not on the known USCIS form list",
        "G-28 ignored: not on the known USCIS form list",
    ]
    assert findings.verification.status == "verified"


@pytest.mark.asyncio
async def test_unknown_forms_alone_are_not_found_not_uncertain(
    directory_web: Path,
) -> None:
    findings = await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        directory_web,
        signals_update={"form_ids": ["I-765", "I-797C (edition 13/45/21)"]},
    )
    form = next(s for s in findings.verification.signals if s.signal == "form_id")
    assert form.state == "not_found"


@pytest.mark.asyncio
async def test_form_printed_twice_is_judged_once(directory_web: Path) -> None:
    findings = await run(
        "uscis_interview.json",
        FakeClient(directory_turns("1-800-555-0100", USA_GOV)),
        directory_web,
        signals_update={"form_ids": ["I-797C", "I-797C (edition 04/01/24)"]},
    )
    form = next(s for s in findings.verification.signals if s.signal == "form_id")
    assert form.evidence == ["I-797C (edition 2024-04-01): known USCIS form (config)"]


@pytest.mark.asyncio
async def test_bot_wall_page_does_not_vouch_for_a_linked_domain(tmp_path: Path) -> None:
    """A 403 .gov page is not evidence, so its links can't make another domain trusted."""
    state_list = "https://www.examplestate.gov/county-offices"
    county_site = "https://www.examplecountyhelp.org/contact"
    web_dir = tmp_path / "web"
    save_fixture(
        web_dir,
        state_list,
        f'<p>Access Denied</p><a href="{county_site}">County</a>',
        status_code=403,
    )
    save_fixture(web_dir, county_site, COUNTY_HTML)
    turns = [
        turn("tool_use", fetch("f1", state_list), fetch("f2", county_site)),
        turn(
            "tool_use",
            submit(
                "(202) 555-0123",
                county_site,
                issuer_official_domain="examplecountyhelp.org",
            ),
        ),
    ]

    findings = await run("county_renewal.json", FakeClient(turns), web_dir)
    v = findings.verification
    assert v.official_phone is None
    assert v.status != "verified"
    assert "examplecountyhelp.org is not a trusted domain" in v.evidence
