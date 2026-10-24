"""Non-immigration letter types: trust models, hints and category scam rules. No network."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from research import checks
from research.deep_pass import RunRecord, replay_deep_pass
from research.deep_verify import Discovery, Submission, org_domain, verify
from research.fetch_tool import (
    WEB_FIXTURES,
    FetchedPage,
    FetchRefused,
    extract_links,
    fetch_page,
    replay_resolver,
    replay_transport,
    save_fixture,
)
from research.hints import HINTS, Hint, Registry, hint_key, where_to_look
from research.models import DeepFindings, LegitimacySignals
from research.scam_rules import scam_red_flags
from tests.research.test_deep_pass import (
    FakeClient,
    fetch,
    load_signals,
    run,
    submit,
    turn,
)

SSA_CONTACT = "https://www.ssa.gov/agency/contact/"
SSA_DIRECTORY = "https://www.usa.gov/agencies/social-security-administration"
SSA_DIRECTORY_HTML = """<h1>Social Security Administration (SSA)</h1>
<p>Website: <a href="http://www.ssa.gov/">Social Security Administration</a></p>
<p>Toll-free number <a href="tel:+18005550100">1-800-555-0100</a></p>"""
MEDICARE_CONTACT = "https://www.medicare.gov/talk-to-someone"
MEDICARE_CONTACT_HTML = """<header>Medicare</header>
<p>Centers for Medicare &amp; Medicaid Services</p>
<h1>Talk to Someone</h1><p>Call <a href="tel:+18005550100">1-800-555-0100</a>.</p>"""


@pytest.mark.parametrize(
    ("doc_type", "key"),
    [
        ("uscis_i797c_asylum_interview", "uscis"),
        ("medicare_summary_notice", "medicare"),
        ("ssa_benefits_notice", "ssa"),
        ("social_security_award_letter", "ssa"),
    ],
)
def test_doc_type_prefixes(doc_type: str, key: str) -> None:
    assert hint_key(doc_type) == key


def test_existing_hints_keep_gov_issuer() -> None:
    for key in ("uscis", "immigration_court", "county_benefits"):
        assert HINTS[key].trust_model == "gov_issuer"


# --- gov_issuer: Medicare / SSA ---


@pytest.mark.asyncio
async def test_ssa_verified_via_usa_gov_when_ssa_gov_blocks(tmp_path: Path) -> None:
    web = tmp_path / "web"
    save_fixture(web, SSA_CONTACT, "Access Denied", status_code=403)
    save_fixture(web, SSA_DIRECTORY, SSA_DIRECTORY_HTML)
    client = FakeClient(
        [
            turn("tool_use", fetch("f1", SSA_CONTACT), fetch("f2", SSA_DIRECTORY)),
            turn(
                "tool_use",
                submit(
                    "1-800-555-0100",
                    SSA_DIRECTORY,
                    issuer_official_domain="ssa.gov",
                    phone_label="Toll-free number",
                ),
            ),
        ]
    )
    findings = await run("ssa_notice.json", client, web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+18005550100"
    assert v.letter_phone_matches is True
    assert any("usa.gov federal directory" in e for e in v.evidence)


@pytest.mark.asyncio
async def test_medicare_verified_on_medicare_gov(tmp_path: Path) -> None:
    web = tmp_path / "web"
    save_fixture(web, MEDICARE_CONTACT, MEDICARE_CONTACT_HTML)
    client = FakeClient(
        [
            turn("tool_use", fetch("f1", MEDICARE_CONTACT)),
            turn(
                "tool_use",
                submit(
                    "1-800-555-0100",
                    MEDICARE_CONTACT,
                    issuer_official_domain="medicare.gov",
                    phone_label="Medicare",
                ),
            ),
        ]
    )
    findings = await run("medicare_summary.json", client, web)
    assert findings.verification.status == "verified"
    assert findings.verification.official_phone == "+18005550100"


@pytest.mark.asyncio
async def test_medicare_scam_is_suspicious_without_web_calls(tmp_path: Path) -> None:
    findings = await run("scam_medicare.json", FakeClient([]), tmp_path)
    v = findings.verification
    assert v.status == "suspicious"
    assert v.official_phone is None
    assert any("free medical tests" in f for f in v.red_flags)
    assert any("Medicare or insurance number by phone" in f for f in v.red_flags)
    assert any("not a .gov website" in f for f in v.red_flags)


# --- Category scam rules ---

MEDICAL = where_to_look("medicare_summary_notice")
HOUSING = where_to_look("housing_authority_recertification")
USCIS = where_to_look("uscis_i797c")


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("Free DNA screening kit for Medicare members", "free medical tests"),
        ("Please call us with your Medicare number", "Medicare or insurance number"),
        ("Text your member ID to this number", "Medicare or insurance number"),
        ("Pay the balance or you will be arrested", "threatens arrest"),
    ],
)
def test_medical_rules(text: str, needle: str) -> None:
    flags = scam_red_flags(
        LegitimacySignals(payment_instructions=text, case_number_format="x"), MEDICAL
    )
    assert any(needle in f for f in flags)


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("Send the security deposit by Zelle to hold the unit", "rental deposit"),
        ("I am overseas on a mission, I will mail you the keys", "landlord is away"),
        ("Pay a $50 fee to get on the Section 8 waiting list", "Section 8"),
        ("Section 8 waitlist registration fee: $40", "Section 8"),
    ],
)
def test_housing_rules(text: str, needle: str) -> None:
    flags = scam_red_flags(
        LegitimacySignals(payment_instructions=text, case_number_format="x"), HOUSING
    )
    assert any(needle in f for f in flags)


def test_legit_section_8_payment_wording_is_not_flagged() -> None:
    text = (
        "The housing assistance payment for your Section 8 voucher goes to the owner."
    )
    signals = LegitimacySignals(payment_instructions=text, case_number_format="x")
    assert scam_red_flags(signals, HOUSING) == []


def test_category_rules_do_not_run_for_immigration() -> None:
    text = "Free DNA screening. Send the deposit by mail. I am overseas."
    signals = LegitimacySignals(payment_instructions=text, case_number_format="x")
    assert scam_red_flags(signals, USCIS) == []


# --- gov_issuer anchored on the state's county-office list (county_benefits) ---

CDSS = "https://www.cdss.ca.gov/county-offices"
CDSS_HTML = """<h1>Contact Your County</h1>
<h2><strong>Example County Social Services</strong></h2>
<p>100 Main Street<br>Springfield, ST 00000<br>(202) 555-0123<br>
<a href="https://www.examplecountyss.org/index.page">Example County Website</a></p>
<h2><strong>Other County Human Services</strong></h2>
<p>(202) 555-0199<br><a href="https://www.othercounty.org/">Other County Website</a></p>"""
COUNTY_SITE = "https://www.examplecountyss.org/contact"
COUNTY_SITE_HTML = """<h1>County of Example, Department of Social Services</h1>
<p>100 Main Street, Springfield, ST 00000</p><p>Call (202) 555-0123</p>"""
OTHER_SITE = "https://www.othercounty.org/contact"
OTHER_SITE_HTML = "<p>Other County. Call (202) 555-0199</p>"


@pytest.fixture
def county_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    save_fixture(web, CDSS, CDSS_HTML)
    save_fixture(web, COUNTY_SITE, COUNTY_SITE_HTML)
    save_fixture(web, OTHER_SITE, OTHER_SITE_HTML)
    return web


def county_turns(phone: str, source: str, domain: str, *urls: str) -> FakeClient:
    fetches = [fetch(f"f{i}", url) for i, url in enumerate(urls)]
    return FakeClient(
        [
            turn("tool_use", *fetches),
            turn(
                "tool_use",
                submit(
                    phone,
                    source,
                    issuer_official_domain=domain,
                    phone_label="Customer service",
                    phone_purpose="Benefits renewal questions",
                ),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_county_site_linked_from_its_state_list_entry_is_verified(
    county_web: Path,
) -> None:
    client = county_turns(
        "(202) 555-0123", COUNTY_SITE, "examplecountyss.org", CDSS, COUNTY_SITE
    )
    findings = await run("county_renewal.json", client, county_web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+12025550123"
    issuer = next(s for s in v.signals if s.signal == "issuer")
    assert issuer.state == "match" and issuer.evidence == [CDSS]
    assert findings.trust_chain == [CDSS, COUNTY_SITE]


@pytest.mark.asyncio
async def test_county_domain_from_another_entry_is_rejected(county_web: Path) -> None:
    client = county_turns(
        "(202) 555-0199", OTHER_SITE, "othercounty.org", CDSS, OTHER_SITE
    )
    findings = await run("county_renewal.json", client, county_web)
    v = findings.verification
    assert v.official_phone is None
    assert "othercounty.org is not the issuer's domain" in v.evidence


COUNTY_GOV = "https://socialservices.examplecounty.gov/contact"


@pytest.mark.asyncio
async def test_unlisted_county_gov_site_naming_the_office_is_accepted(
    county_web: Path,
) -> None:
    save_fixture(county_web, COUNTY_GOV, COUNTY_SITE_HTML)
    client = county_turns(
        "(202) 555-0123",
        COUNTY_GOV,
        "socialservices.examplecounty.gov",
        CDSS,
        COUNTY_GOV,
    )
    findings = await run("county_renewal.json", client, county_web)
    assert findings.verification.official_phone == "+12025550123"
    assert findings.verification.status == "verified"


@pytest.mark.asyncio
async def test_unlisted_gov_site_not_naming_the_office_is_rejected(
    county_web: Path,
) -> None:
    save_fixture(county_web, COUNTY_GOV, "<p>Some other office. (202) 555-0123</p>")
    client = county_turns(
        "(202) 555-0123",
        COUNTY_GOV,
        "socialservices.examplecounty.gov",
        CDSS,
        COUNTY_GOV,
    )
    findings = await run("county_renewal.json", client, county_web)
    assert findings.verification.official_phone is None
    assert any("not the issuer's domain" in e for e in findings.verification.evidence)


@pytest.mark.asyncio
async def test_state_list_entry_number_used_when_county_site_blocked(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    save_fixture(web, CDSS, CDSS_HTML)
    save_fixture(web, COUNTY_SITE, "Access Denied", status_code=403)
    client = county_turns(
        "(202) 555-0123", CDSS, "examplecountyss.org", CDSS, COUNTY_SITE
    )
    findings = await run("county_renewal.json", client, web)
    v = findings.verification
    assert v.official_phone == "+12025550123"
    assert v.status == "verified"
    assert any("this office's entry on" in e for e in v.evidence)


@pytest.mark.asyncio
async def test_another_countys_number_on_the_state_list_is_rejected(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    save_fixture(web, CDSS, CDSS_HTML)
    save_fixture(web, COUNTY_SITE, "Access Denied", status_code=403)
    client = county_turns(
        "(202) 555-0199", CDSS, "examplecountyss.org", CDSS, COUNTY_SITE
    )
    findings = await run("county_renewal.json", client, web)
    v = findings.verification
    assert v.official_phone is None
    assert any("not in this office's entry" in e for e in v.evidence)


@pytest.mark.asyncio
async def test_unlisted_non_gov_county_domain_is_not_trusted(tmp_path: Path) -> None:
    web = tmp_path / "web"
    save_fixture(web, COUNTY_SITE, COUNTY_SITE_HTML)
    client = county_turns(
        "(202) 555-0123", COUNTY_SITE, "examplecountyss.org", COUNTY_SITE
    )
    findings = await run("county_renewal.json", client, web)
    assert findings.verification.official_phone is None
    assert findings.verification.status == "unknown"


def test_registry_entry_stops_at_the_next_entry() -> None:
    entry = checks.registry_entry(CDSS_HTML, "Example County")
    assert entry is not None
    assert checks.phone_on_page("+12025550123", entry)
    assert not checks.phone_on_page("+12025550199", entry)
    assert checks.registry_entry(CDSS_HTML, "Ample County") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.uscis.gov/contactcenter", "uscis.gov"),
        ("www.monocounty.ca.gov", "monocounty.ca.gov"),
        ("https://dpss.lacounty.gov/en.html", "lacounty.gov"),
        ("ca.gov", ""),
        ("examplecountyss.org", "examplecountyss.org"),
    ],
)
def test_org_domain_keeps_hosts_under_state_suffixes(raw: str, expected: str) -> None:
    assert org_domain(raw) == expected


# --- Recorded live runs, replayed offline from fixtures/web ---


async def replay(signals_name: str) -> DeepFindings:
    signals, _, _ = load_signals(f"{signals_name}.json")
    record = RunRecord.model_validate_json(
        (WEB_FIXTURES / "runs" / f"{signals_name}.json").read_text()
    )
    async with httpx.AsyncClient(transport=replay_transport()) as http:
        return await replay_deep_pass(
            signals, record, http=http, resolve=replay_resolver
        )


@pytest.mark.asyncio
async def test_recorded_medi_cal_letter_verified_from_the_cdss_entry() -> None:
    findings = await replay("medi_cal_alameda")
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+15102632420"
    assert v.letter_phone_matches is True
    assert findings.trust_chain == [CDSS]


# --- registry_linked: housing authority via HUD's PHA list ---

HUD_LIST = "https://www.hud.gov/sites/dfiles/PIH/documents/PHA_Contact_Report_ST.pdf"
# What fetch_page makes of the PDF: its layout text in a <pre>.
HUD_LIST_HTML = """<pre>PHA Contact Information
   PHA Code    Name, Phone, Fax, Email                Physical Address     Type
      ST001    Example Housing Authority              100 MAIN STREET      Combined
               Phone:   (202)555-0161                 SPRINGFIELD
               Fax:     (202)555-0162                 ST ,  00000
               Email:   info@examplehousing.org
      ST002    Other Housing Authority                9 ELM STREET         Section 8
               Phone:   (202)555-0171                 SPRINGFIELD
               Fax:                                   ST ,  00000
      ST003    Example Housing Authority              5 OAK AVENUE         Section 8
               Phone:   (202)555-0181                 SHELBYVILLE
</pre>"""
PHA_SITE = "https://www.examplehousing.org/contact"
PHA_SITE_HTML = "<h1>Example Housing Authority</h1><p>Call (202) 555-0161</p>"
CITY_PAGE = "https://www.springfield.gov/housing"
CITY_PAGE_HTML = '<a href="https://www.examplehousing.org/">Housing authority</a>'


@pytest.fixture
def hud_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    save_fixture(web, HUD_LIST, HUD_LIST_HTML)
    save_fixture(web, PHA_SITE, PHA_SITE_HTML)
    save_fixture(web, CITY_PAGE, CITY_PAGE_HTML)
    return web


def pha_turns(phone: str, source: str, *urls: str, label: str = "Phone") -> FakeClient:
    return FakeClient(
        [
            turn("tool_use", *[fetch(f"f{i}", u) for i, u in enumerate(urls)]),
            turn(
                "tool_use",
                submit(
                    phone,
                    source,
                    issuer_official_domain="examplehousing.org",
                    phone_label=label,
                    phone_purpose="Recertification appointments",
                ),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_registry_entry_naming_the_org_gives_a_verified_number(
    hud_web: Path,
) -> None:
    client = pha_turns("(202) 555-0161", HUD_LIST, HUD_LIST)
    findings = await run("housing_authority_recert.json", client, hud_web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+12025550161"
    assert v.letter_phone_matches is True
    issuer = next(s for s in v.signals if s.signal == "issuer")
    assert issuer.state == "match" and issuer.evidence == [HUD_LIST]
    assert any("this organization's entry on" in e for e in v.evidence)


@pytest.mark.asyncio
async def test_registry_fax_number_is_not_accepted(hud_web: Path) -> None:
    client = pha_turns("(202) 555-0162", HUD_LIST, HUD_LIST)
    findings = await run("housing_authority_recert.json", client, hud_web)
    assert findings.verification.official_phone is None
    assert any(
        "not this organization's listed number" in e
        for e in findings.verification.evidence
    )


@pytest.mark.asyncio
async def test_registry_number_of_another_org_is_not_accepted(hud_web: Path) -> None:
    client = pha_turns("(202) 555-0171", HUD_LIST, HUD_LIST)
    findings = await run("housing_authority_recert.json", client, hud_web)
    assert findings.verification.official_phone is None


@pytest.mark.asyncio
async def test_same_name_in_another_city_is_not_the_org(hud_web: Path) -> None:
    client = pha_turns("(202) 555-0181", HUD_LIST, HUD_LIST)
    findings = await run(
        "housing_authority_recert.json",
        client,
        hud_web,
        signals_update={"return_address": "5 Oak Avenue, Shelbyville, ST 00000"},
    )
    accepted = findings.verification.evidence[0]
    assert accepted.startswith("Official number found in this organization's entry")
    findings = await run(
        "housing_authority_recert.json",
        pha_turns("(202) 555-0181", HUD_LIST, HUD_LIST),
        hud_web,
    )
    assert "not this organization's listed number" in findings.verification.evidence[0]


@pytest.mark.asyncio
async def test_org_domain_not_on_the_registry_is_rejected(hud_web: Path) -> None:
    """examplehousing.org is linked from a .gov page, but HUD's entry doesn't link to it."""
    client = pha_turns("(202) 555-0161", PHA_SITE, HUD_LIST, CITY_PAGE, PHA_SITE)
    findings = await run("housing_authority_recert.json", client, hud_web)
    v = findings.verification
    assert v.official_phone is None
    assert (
        "examplehousing.org is neither this organization's registry entry"
        in v.evidence[0]
    )


@pytest.mark.asyncio
async def test_org_missing_from_the_registry_is_unknown(hud_web: Path) -> None:
    client = pha_turns("(202) 555-0161", HUD_LIST, HUD_LIST)
    findings = await run(
        "housing_authority_recert.json",
        client,
        hud_web,
        signals_update={"letterhead": "Springfield Rental Services"},
    )
    v = findings.verification
    assert v.status == "unknown"
    assert v.official_phone is None
    issuer = next(s for s in v.signals if s.signal == "issuer")
    assert issuer.evidence == [
        "This organization was not found in the HUD Public Housing Agency contact list"
    ]


def test_registry_page_without_entries_has_no_entry() -> None:
    picker = (
        "<html><body><h1>PHA Contact Information</h1><p>Pick a state.</p></body></html>"
    )
    assert (
        checks.text_entry(picker, "Example Housing Authority", r"^\s*[A-Z]{2}\d{3}\s")
        is None
    )


# Path (b) needs a registry whose entries link to the org's site; HUD's list has
# none, so this uses a heading-style registry hint built for the test.
LINKING_HINT = Hint(
    depth="shallow",
    category="medical",
    trust_model="registry_linked",
    registries=[
        Registry(
            name="Example registry", domain="registry.example.gov", returns_phone=False
        )
    ],
)
REGISTRY_PAGE = "https://registry.example.gov/list"
REGISTRY_HTML = """<h2>Example Clinic</h2><p><a href="https://www.exampleclinic.org/">Website</a></p>
<h2>Other Clinic</h2><p><a href="https://www.otherclinic.org/">Website</a></p>"""


def linking_findings(source: str, html: str, domain: str) -> DeepFindings:
    def page(url: str, body: str) -> FetchedPage:
        return FetchedPage(
            url=url,
            final_url=url,
            status_code=200,
            html=body,
            links=extract_links(body, url),
            fetched_at=datetime.now(UTC),
        )

    discovery = Discovery(
        pages=[page(REGISTRY_PAGE, REGISTRY_HTML), page(source, html)],
        submission=Submission(
            issuer_official_domain=domain,
            official_phone="(202) 555-0191",
            phone_source_url=source,
        ),
    )
    signals = LegitimacySignals(letterhead="Example Clinic")
    findings, _, _ = verify(signals, LINKING_HINT, None, [], discovery)
    return findings


def test_registry_path_b_number_on_the_linked_org_site_is_accepted() -> None:
    findings = linking_findings(
        "https://www.exampleclinic.org/billing",
        "<p>(202) 555-0191</p>",
        "exampleclinic.org",
    )
    assert findings.verification.official_phone is None  # 1 match only: not verified
    assert findings.alternative_contacts[0].phone == "+12025550191"
    assert (
        "the website the official registry lists" in findings.verification.evidence[0]
    )


def test_registry_path_b_site_linked_from_another_entry_is_rejected() -> None:
    findings = linking_findings(
        "https://www.otherclinic.org/billing",
        "<p>(202) 555-0191</p>",
        "otherclinic.org",
    )
    assert findings.alternative_contacts == []
    assert "otherclinic.org is neither" in findings.verification.evidence[0]


# --- fetch_tool: non-HTML only for configured registry documents ---


async def fetch_with(url: str, content_type: str, body: bytes) -> FetchedPage:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200, headers={"content-type": content_type}, content=body
        )
    )
    async with httpx.AsyncClient(transport=transport) as http:
        return await fetch_page(url, http=http, resolve=replay_resolver)


@pytest.mark.asyncio
async def test_pdf_refused_outside_the_registry_allowlist() -> None:
    with pytest.raises(FetchRefused, match="not HTML or text"):
        await fetch_with(
            "https://www.hud.gov/other.pdf", "application/pdf", b"%PDF-1.4"
        )


@pytest.mark.asyncio
async def test_unreadable_registry_pdf_is_refused() -> None:
    with pytest.raises(FetchRefused, match="could not read the PDF"):
        await fetch_with(HUD_LIST, "application/pdf", b"not a pdf")


@pytest.mark.asyncio
async def test_recorded_housing_authority_verified_from_the_hud_pdf_entry() -> None:
    findings = await replay("housing_authority_oakland")
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+15108741500"
    assert v.letter_phone_matches is True
    assert findings.trust_chain == [
        "https://www.hud.gov/sites/dfiles/PIH/documents/PHA_Contact_Report_CA.pdf"
    ]


@pytest.mark.asyncio
async def test_rental_deposit_scam_is_suspicious_without_web_calls(
    tmp_path: Path,
) -> None:
    findings = await run("scam_rental_deposit.json", FakeClient([]), tmp_path)
    v = findings.verification
    assert v.status == "suspicious"
    assert v.official_phone is None
    assert any("rental deposit" in f for f in v.red_flags)
    assert any("landlord is away" in f for f in v.red_flags)


# --- gov_issuer on the county court's own .gov host (eviction papers) ---

COURT = "https://www.example.courts.ca.gov/civil"
COURT_HTML = """<header>Superior Court of California | County of Example</header>
<h1>Civil: unlawful detainer (eviction)</h1>
<p>Forms: Summons (SUM-130). Clerk's office: 100 Main Street, Springfield, ST 00000.
Call <a href="tel:+12025550141">(202) 555-0141</a>.</p>"""
OTHER_COURT = "https://www.other.courts.ca.gov/civil"
OTHER_COURT_HTML = """<header>Superior Court of California | County of Other</header>
<p>Call (202) 555-0142.</p>"""


@pytest.fixture
def court_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    save_fixture(web, COURT, COURT_HTML)
    save_fixture(web, OTHER_COURT, OTHER_COURT_HTML)
    return web


def court_turns(phone: str, source: str, domain: str) -> FakeClient:
    return FakeClient(
        [
            turn("tool_use", fetch("f1", source)),
            turn(
                "tool_use",
                submit(
                    phone,
                    source,
                    issuer_official_domain=domain,
                    phone_label="Civil clerk",
                    phone_purpose="Unlawful detainer cases",
                ),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_eviction_summons_verified_on_the_county_court_site(
    court_web: Path,
) -> None:
    client = court_turns("(202) 555-0141", COURT, "www.example.courts.ca.gov")
    findings = await run("eviction_summons.json", client, court_web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+12025550141"
    states = {s.signal: s.state for s in v.signals}
    assert states["issuer"] == states["form_id"] == states["url_domains"] == "match"


@pytest.mark.asyncio
async def test_another_countys_court_is_not_the_issuer(court_web: Path) -> None:
    client = court_turns("(202) 555-0142", OTHER_COURT, "other.courts.ca.gov")
    findings = await run("eviction_summons.json", client, court_web)
    v = findings.verification
    assert v.official_phone is None
    assert v.status == "unknown"
    assert findings.alternative_contacts[0].name == "The court's Self-Help Center"


@pytest.mark.asyncio
async def test_recorded_eviction_summons_verified_with_self_help_alternative() -> None:
    findings = await replay("eviction_alameda")
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+15102676911"
    url_domains = next(s for s in v.signals if s.signal == "url_domains")
    assert url_domains.evidence == [
        "alameda.courts.ca.gov is the issuer's official domain"
    ]
    self_help = findings.alternative_contacts[0]
    assert "Self-Help" in self_help.name and self_help.phone == "+15102721393"


# --- registry_linked: hospital / clinic via the CMS NPI Registry API ---

NPI_API = (
    "https://npiregistry.cms.hhs.gov/api/?version=2.1&enumeration_type=NPI-2"
    "&organization_name=example%20medical%20center&city=springfield&state=ST"
)
NPI_JSON = {
    "result_count": 2,
    "results": [
        {
            "number": "1234567893",
            "basic": {
                "organization_name": "EXAMPLE MEDICAL CENTER",
                "authorized_official_telephone_number": "2025550159",
            },
            "other_names": [],
            "addresses": [
                {
                    "address_purpose": "MAILING",
                    "address_1": "PO BOX 9",
                    "city": "CAPITAL CITY",
                    "state": "ST",
                    "telephone_number": "202-555-0158",
                    "fax_number": "202-555-0157",
                },
                {
                    "address_purpose": "LOCATION",
                    "address_1": "100 MAIN STREET",
                    "city": "SPRINGFIELD",
                    "state": "ST",
                    "postal_code": "00000",
                    "telephone_number": "202-555-0151",
                    "fax_number": "202-555-0152",
                },
            ],
        },
        {
            "number": "1234567802",
            "basic": {"organization_name": "OTHER CLINIC"},
            "addresses": [
                {
                    "address_purpose": "LOCATION",
                    "city": "SPRINGFIELD",
                    "telephone_number": "202-555-0153",
                }
            ],
        },
    ],
}


@pytest.fixture
def npi_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    save_fixture(
        web,
        NPI_API,
        json.dumps(NPI_JSON),
        headers={"content-type": "application/json"},
    )
    return web


def npi_turns(phone: str) -> FakeClient:
    return FakeClient(
        [
            turn("tool_use", fetch("f1", NPI_API)),
            turn(
                "tool_use",
                submit(phone, NPI_API, issuer_official_domain=None, phone_label="Main"),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_npi_entry_naming_the_org_gives_a_verified_number(npi_web: Path) -> None:
    findings = await run("hospital_bill.json", npi_turns("202-555-0151"), npi_web)
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+12025550151"
    assert v.letter_phone_matches is True
    assert findings.trust_chain == [NPI_API]


@pytest.mark.parametrize(
    "phone",
    [
        "202-555-0152",  # location fax
        "202-555-0158",  # mailing phone
        "202-555-0157",  # mailing fax
        "202-555-0159",  # authorized official
        "202-555-0153",  # another organization
    ],
)
@pytest.mark.asyncio
async def test_npi_only_the_practice_location_phone_counts(
    npi_web: Path, phone: str
) -> None:
    findings = await run("hospital_bill.json", npi_turns(phone), npi_web)
    assert findings.verification.official_phone is None
    assert "not this organization's listed number" in findings.verification.evidence[0]


@pytest.mark.asyncio
async def test_npi_org_in_another_city_is_not_found(npi_web: Path) -> None:
    findings = await run(
        "hospital_bill.json",
        npi_turns("202-555-0151"),
        npi_web,
        signals_update={"return_address": "1 Elm Street, Shelbyville, ST 00000"},
    )
    v = findings.verification
    assert v.status == "unknown"
    assert v.official_phone is None
    issuer = next(s for s in v.signals if s.signal == "issuer")
    assert issuer.evidence == [
        "This organization was not found in the CMS NPI Registry"
    ]


@pytest.mark.asyncio
async def test_json_refused_outside_the_registry_allowlist() -> None:
    with pytest.raises(FetchRefused, match="not HTML or text"):
        await fetch_with("https://www.example.gov/api", "application/json", b"{}")


@pytest.mark.asyncio
async def test_recorded_hospital_bill_verified_from_the_npi_registry() -> None:
    findings = await replay("hospital_bill_alameda")
    v = findings.verification
    assert v.status == "verified"
    assert v.official_phone == "+15104374800"
    assert findings.trust_chain[0].startswith("https://npiregistry.cms.hhs.gov/api/")


# --- unverifiable_private: property manager / individual landlord ---

PM_SITE = "https://www.examplepm.com/contact"
PM_SITE_HTML = "<p>Example Property Management. Call (202) 555-0111</p>"
SELF_HELP = "https://www.example.courts.ca.gov/self-help"
SELF_HELP_HTML = """<h1>Self-Help Center</h1><p>Call (202) 555-0121.
See also <a href="https://www.tenantsunion.org/">the tenants union</a>.</p>"""
TENANT_ORG = "https://www.tenantsunion.org/help"
TENANT_ORG_HTML = "<p>Tenant hotline (202) 555-0122</p>"


@pytest.mark.asyncio
async def test_property_manager_is_unknown_with_only_gov_alternative_numbers(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    save_fixture(web, PM_SITE, PM_SITE_HTML)
    save_fixture(web, SELF_HELP, SELF_HELP_HTML)
    save_fixture(web, TENANT_ORG, TENANT_ORG_HTML)
    client = FakeClient(
        [
            turn(
                "tool_use",
                fetch("f1", PM_SITE),
                fetch("f2", SELF_HELP),
                fetch("f3", TENANT_ORG),
            ),
            turn(
                "tool_use",
                submit(
                    "(202) 555-0111",
                    PM_SITE,
                    issuer_official_domain="examplepm.com",
                    alternative_contacts=[
                        {
                            "name": "Court Self-Help Center",
                            "purpose": "Tenant help",
                            "phone": "(202) 555-0121",
                            "source_url": SELF_HELP,
                        },
                        {
                            "name": "Tenants union",
                            "purpose": "Tenant hotline",
                            "phone": "(202) 555-0122",
                            "source_url": TENANT_ORG,
                        },
                    ],
                ),
            ),
        ]
    )
    findings = await run("property_manager_notice.json", client, web)
    v = findings.verification
    assert v.status == "unknown"
    assert v.official_phone is None
    assert v.evidence[0] == (
        "This kind of sender can't be verified from public sources, "
        "so no number is accepted"
    )
    contacts = {c.name: c for c in findings.alternative_contacts}
    assert contacts["Court Self-Help Center"].phone == "+12025550121"
    assert contacts["Tenants union"].phone is None  # not a .gov page
    assert contacts["Tenants union"].url == TENANT_ORG
    assert "The county court's Self-Help Center" in contacts


@pytest.mark.asyncio
async def test_property_manager_deposit_scam_is_suspicious(tmp_path: Path) -> None:
    findings = await run(
        "property_manager_notice.json",
        FakeClient([]),
        tmp_path,
        signals_update={
            "payment_instructions": "Wire the deposit today to hold your unit."
        },
    )
    v = findings.verification
    assert v.status == "suspicious"
    assert any("rental deposit" in f for f in v.red_flags)


@pytest.mark.asyncio
async def test_individual_landlord_is_unknown_with_alternatives(
    tmp_path: Path,
) -> None:
    findings = await run("private_landlord_notice.json", FakeClient([]), tmp_path)
    v = findings.verification
    assert v.status == "unknown"
    assert v.official_phone is None
    assert v.red_flags == []
    assert [c.name for c in findings.alternative_contacts] == [
        "Local tenant rights organization",
        "City or county housing department",
    ]
