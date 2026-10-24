"""Where the deep pass should look, by document type. Config, not letter-specific logic.

Never put a phone number here (C32): official numbers are looked up at run time.
"""

import re
from typing import Literal

from pydantic import BaseModel

from app.contracts import (
    LegitimacySignals,
)

# Sites that republish agency numbers. Their numbers can be stale or planted, so
# the fetch tool refuses them and web search never returns them.
BLOCKED_DOMAINS: tuple[str, ...] = (
    "gethuman.com",
    "800notes.com",
    "whocalled.us",
    "whocallsme.com",
    "callercenter.com",
    "whitepages.com",
    "yellowpages.com",
    "yelp.com",
    "customerservicenumbers.com",
    "customerservicenumber.org",
    "contactnumbers.org",
    "contacthelp.com",
    "customercarecontacts.com",
    "phonenumbers.how",
    "numberbarn.com",
    "usa-customer-service.com",
)

# Identifier shapes that must never leave in a URL (receipt number, A-Number, SSN, MBI).
ID_SHAPED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z])[a-z]{3}\d{10}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![a-z])a-?\d{8,9}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    # Medicare Beneficiary Identifier, e.g. 1EG4-TE5-MK73.
    re.compile(
        r"(?<![a-z0-9])[1-9][a-z][a-z0-9]\d-?[a-z][a-z0-9]\d-?[a-z]{2}\d{2}(?![a-z0-9])",
        re.IGNORECASE,
    ),
)


# The only non-HTML responses fetch_page reads, by URL prefix: official registry
# data that is published only as a PDF or a JSON API.
REGISTRY_DOCUMENTS: tuple[tuple[str, str], ...] = (
    (
        "https://www.hud.gov/sites/dfiles/PIH/documents/PHA_Contact_Report_",
        "application/pdf",
    ),
    ("https://npiregistry.cms.hhs.gov/api/", "application/json"),
)


# Words in a number's label that mark a special-purpose line, never the main one.
SECONDARY_LINE_WORDS: tuple[str, ...] = (
    "tty",
    "tdd",
    "teletype",
    "relay",
    "military",
    "fax",
    "international",
    "overseas",
    "outside the u.s",
)


class PurposePage(BaseModel):
    """Which kind of official page answers a given call purpose."""

    keywords: list[str]
    page_kind: str


Category = Literal["immigration", "housing", "medical", "benefits"]
TrustModel = Literal["gov_issuer", "registry_linked", "unverifiable_private"]
"""Who vouches for the official number:
- gov_issuer: the issuer's own .gov site (plus its .gov directory fallback);
- registry_linked: a government registry entry that names the org;
- unverifiable_private: nobody public, so no number is ever accepted."""


class Registry(BaseModel):
    """A government list of organizations of one kind, with one entry per org.

    Its entry for the org vouches for it: by showing the number, or by linking
    to the org's own domain. Used by registry_linked hints, and by gov_issuer
    hints whose issuer domain must be discovered (e.g. the county office).
    """

    name: str
    domain: str
    url: str | None = None
    """The list page, when there is one fixed page."""
    search_terms: list[str] = []
    match_fields: list[Literal["name", "county", "city", "npi"]] = ["name"]
    returns_phone: bool = False
    """True if the registry entry itself shows the org's phone number."""
    entry_start: str | None = None
    """For a plain-text list (e.g. a PDF): regex for the line that starts each
    entry. When unset, each entry starts at a heading."""
    phone_line: str | None = None
    """Regex for the entry line holding the main number (e.g. `Phone:`, not
    `Fax:`). When unset, a number anywhere in the entry counts."""
    api: Literal["npi"] | None = None
    """Set when the registry is a JSON API whose results are read as entries."""


class Hint(BaseModel):
    depth: Literal["deep", "shallow", "unverifiable"]
    category: Category | None = None
    trust_model: TrustModel = "gov_issuer"
    registries: list[Registry] = []
    issuer_short: str | None = None
    federal: bool = False
    anchor_domains: list[str] = []
    issuer_domains: list[str] = []
    """When set, the official number must come from one of these domains. When
    empty, the issuer's own domain is discovered (e.g. a county office)."""
    issuer_names: list[str] = []
    """Official names of the issuer, used to check a directory page is about it."""
    directory_domains: list[str] = []
    """Official government directories (.gov) whose page for this issuer may stand in
    for the issuer's own site, only when that site can't be fetched."""
    search_terms: list[str] = []
    look_for: str = "the issuer's official contact page"
    purpose_pages: dict[str, PurposePage] = {}
    default_purpose: str = "general"
    known_forms: list[str] = []
    case_number_shape: tuple[int, int] | None = None
    """(letters, digits) of the case number, e.g. (3, 10)."""
    letterhead_keywords: list[str] = []
    alternatives: list[tuple[str, str]] = []
    """(name, purpose) suggestions offered when the letter can't be verified."""
    issuer_domain_named: bool = False
    """For a discovered issuer domain: count it only if it is .gov and one of its
    fetched pages names the letterhead office and county (e.g. one county's
    court among the many on courts.ca.gov)."""


HINTS: dict[str, Hint] = {
    "uscis": Hint(
        depth="deep",
        category="immigration",
        trust_model="gov_issuer",
        issuer_short="USCIS",
        federal=True,
        anchor_domains=["uscis.gov"],
        issuer_domains=["uscis.gov"],
        issuer_names=["U.S. Citizenship and Immigration Services"],
        directory_domains=["usa.gov"],
        search_terms=["USCIS Contact Center phone number site:uscis.gov"],
        look_for="the USCIS Contact Center page on uscis.gov",
        purpose_pages={
            "case_questions": PurposePage(
                keywords=[
                    "appointment",
                    "interview",
                    "reschedule",
                    "schedule",
                    "case",
                    "status",
                    "notice",
                    "interpreter",
                ],
                page_kind="the USCIS Contact Center page (uscis.gov/contactcenter), "
                "which lists the phone number for questions about an existing case or appointment",
            ),
        },
        default_purpose="case_questions",
        known_forms=["I-797", "I-797A", "I-797B", "I-797C", "I-797D", "I-589"],
        case_number_shape=(3, 10),
        letterhead_keywords=["citizenship and immigration", "uscis"],
        alternatives=[
            (
                "DOJ-recognized legal service providers (EOIR list)",
                "Free or low-cost immigration legal help",
            )
        ],
    ),
    "immigration_court": Hint(
        depth="deep",
        category="immigration",
        trust_model="gov_issuer",
        issuer_short="the Immigration Court (EOIR)",
        federal=True,
        anchor_domains=["justice.gov"],
        issuer_domains=["justice.gov"],
        search_terms=["EOIR immigration court contact site:justice.gov/eoir"],
        look_for="the EOIR pages on justice.gov/eoir (automated case information line or the court's page)",
        purpose_pages={
            "case_questions": PurposePage(
                keywords=["hearing", "court", "case", "judge", "status"],
                page_kind="the EOIR page with the automated case information line, "
                "or the specific immigration court's page",
            ),
        },
        default_purpose="case_questions",
        known_forms=["EOIR-26", "EOIR-28", "EOIR-33", "EOIR-42A", "EOIR-42B"],
        letterhead_keywords=["executive office for immigration review", "eoir"],
    ),
    "county_benefits": Hint(
        depth="shallow",
        category="benefits",
        trust_model="gov_issuer",
        registries=[
            Registry(
                name="California Department of Social Services county offices list",
                domain="cdss.ca.gov",
                url="https://www.cdss.ca.gov/county-offices",
                match_fields=["county"],
                returns_phone=True,
            )
        ],
        search_terms=[
            "{county} county social services office phone",
            "California county social services offices site:cdss.ca.gov",
        ],
        look_for="the state's official list of county offices (cdss.ca.gov/county-offices), "
        "then the county office site that the county's entry links to",
        purpose_pages={
            "renewal": PurposePage(
                keywords=["renew", "renewal", "redetermination", "benefits", "case"],
                page_kind="the county benefits office contact page",
            ),
        },
        default_purpose="renewal",
        letterhead_keywords=["county", "social services", "human services"],
    ),
    "housing_authority": Hint(
        depth="shallow",
        category="housing",
        trust_model="registry_linked",
        registries=[
            Registry(
                name="HUD Public Housing Agency contact list",
                domain="hud.gov",
                url="https://www.hud.gov/contactus/public-housing-contacts",
                match_fields=["name", "city"],
                returns_phone=True,
                entry_start=r"^\s*[A-Z]{2}\d{3}\s",
                phone_line=r"^\s*Phone:",
            )
        ],
        anchor_domains=["hud.gov"],
        search_terms=[
            "{county} housing authority contact",
            "HUD public housing agency contact list",
        ],
        look_for="HUD's PHA contact list on hud.gov (the state's PDF) and this housing "
        "authority's own entry in it",
        purpose_pages={
            "housing_case": PurposePage(
                keywords=[
                    "voucher",
                    "section 8",
                    "recertification",
                    "housing",
                    "lease",
                ],
                page_kind="the housing authority's contact page",
            ),
        },
        default_purpose="housing_case",
        letterhead_keywords=["housing authority", "housing and urban development"],
    ),
    "private_landlord": Hint(
        depth="unverifiable",
        category="housing",
        trust_model="gov_issuer",
        alternatives=[
            ("Local tenant rights organization", "Free advice on landlord notices"),
            ("City or county housing department", "Questions about tenant rights"),
        ],
    ),
    "eviction_court": Hint(
        depth="deep",
        category="housing",
        trust_model="gov_issuer",
        issuer_short="the court",
        issuer_domain_named=True,
        search_terms=[
            "Superior Court of California County of {county} civil unlawful detainer contact",
            "{county} superior court self-help center eviction",
        ],
        look_for="the county superior court's own .gov site (most are <county>.courts.ca.gov) "
        "and its civil / unlawful detainer clerk contact page",
        purpose_pages={
            "eviction_case": PurposePage(
                keywords=[
                    "eviction",
                    "unlawful detainer",
                    "summons",
                    "answer",
                    "hearing",
                    "trial",
                    "case",
                ],
                page_kind="the court's civil / unlawful detainer clerk contact page, "
                "or its Self-Help Center page",
            ),
        },
        default_purpose="eviction_case",
        known_forms=["SUM-130", "UD-100", "UD-101", "UD-105"],
        letterhead_keywords=["superior court"],
        alternatives=[
            (
                "The court's Self-Help Center",
                "Free help with responding to eviction papers",
            ),
            (
                "Local legal aid or tenant rights organization",
                "Free legal advice for tenants facing eviction",
            ),
        ],
    ),
    "hospital_provider": Hint(
        depth="shallow",
        category="medical",
        trust_model="registry_linked",
        registries=[
            Registry(
                name="CMS NPI Registry",
                domain="npiregistry.cms.hhs.gov",
                url="https://npiregistry.cms.hhs.gov/api/?version=2.1"
                "&enumeration_type=NPI-2&organization_name=<name>&city=<city>&state=<ST>",
                match_fields=["name", "city"],
                returns_phone=True,
                api="npi",
                phone_line=r"^Practice location phone:",
            )
        ],
        search_terms=["{issuer} patient billing phone"],
        look_for="the organization's entry in the CMS NPI Registry API (organizations, "
        "queried by name, city and state)",
        purpose_pages={
            "billing": PurposePage(
                keywords=[
                    "bill",
                    "balance",
                    "charge",
                    "payment",
                    "insurance",
                    "statement",
                    "financial assistance",
                ],
                page_kind="the organization's NPI Registry entry (practice location "
                "phone)",
            ),
        },
        default_purpose="billing",
        # Any provider organization has an NPI entry, not just hospitals.
        letterhead_keywords=[
            "hospital",
            "medical center",
            "health system",
            "medical group",
            "health center",
            "clinic",
            "dental",
            "pharmacy",
            "urgent care",
        ],
        alternatives=[
            (
                "The hospital's financial assistance (charity care) office",
                "Ask whether this bill qualifies for financial assistance",
            )
        ],
    ),
    "property_manager": Hint(
        # California's DRE license lookup is POST-only, which fetch_page can't
        # use, so a management company can't be tied to a registry entry.
        depth="shallow",
        category="housing",
        trust_model="unverifiable_private",
        search_terms=[
            "{county} county superior court self-help center eviction",
            "{county} tenant rights office site:.gov",
        ],
        look_for="official .gov help for tenants: the county court's self-help "
        "center and the city or county tenant / housing office",
        alternatives=[
            (
                "The county court's Self-Help Center",
                "Free help understanding landlord and eviction notices",
            ),
            (
                "City or county tenant / housing office",
                "Questions about tenant rights and rent rules",
            ),
        ],
    ),
    "health_insurer": Hint(
        # No public registry entry ties an insurer to its phone line, but the
        # member already holds a number they can trust: the one on their card.
        depth="unverifiable",
        category="medical",
        trust_model="unverifiable_private",
        letterhead_keywords=["health plan", "health insurance company"],
        alternatives=[
            (
                "Member services number on your insurance card",
                "The plan's own line for questions about coverage, claims or bills",
            ),
            (
                "State health plan help center (DMHC in California)",
                "Free help if the plan won't resolve a problem",
            ),
        ],
    ),
    "medicare": Hint(
        depth="deep",
        category="medical",
        trust_model="gov_issuer",
        issuer_short="Medicare",
        federal=True,
        anchor_domains=["medicare.gov"],
        issuer_domains=["medicare.gov", "cms.gov"],
        issuer_names=["Centers for Medicare & Medicaid Services"],
        directory_domains=["usa.gov"],
        search_terms=["Medicare contact phone number site:medicare.gov"],
        look_for="the Medicare contact page on medicare.gov (Talk to Someone)",
        purpose_pages={
            "medicare_questions": PurposePage(
                keywords=[
                    "claim",
                    "bill",
                    "coverage",
                    "notice",
                    "summary",
                    "enroll",
                    "premium",
                    "card",
                    "plan",
                ],
                page_kind="the medicare.gov Talk to Someone page, which lists the main "
                "Medicare help line",
            ),
        },
        default_purpose="medicare_questions",
        letterhead_keywords=["medicare", "centers for medicare"],
        alternatives=[
            (
                "State Health Insurance Assistance Program (SHIP)",
                "Free, unbiased Medicare counseling",
            )
        ],
    ),
    "ssa": Hint(
        depth="deep",
        category="benefits",
        trust_model="gov_issuer",
        issuer_short="Social Security (SSA)",
        federal=True,
        anchor_domains=["ssa.gov"],
        issuer_domains=["ssa.gov"],
        issuer_names=["Social Security Administration"],
        directory_domains=["usa.gov"],
        search_terms=[
            "Social Security Administration contact phone number site:ssa.gov"
        ],
        look_for="the Social Security contact page on ssa.gov",
        purpose_pages={
            "benefits_questions": PurposePage(
                keywords=[
                    "benefit",
                    "payment",
                    "appointment",
                    "notice",
                    "card",
                    "medicare",
                    "ssi",
                    "disability",
                    "retirement",
                ],
                page_kind="the ssa.gov contact page with the main Social Security number",
            ),
        },
        default_purpose="benefits_questions",
        letterhead_keywords=["social security administration"],
    ),
}

DEFAULT_HINT = Hint(depth="shallow", search_terms=["{issuer} official contact"])

# doc_type prefixes Track A may emit, mapped to a hint key.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("uscis", "uscis"),
    ("dhs_uscis", "uscis"),
    ("immigration_court", "immigration_court"),
    ("eoir", "immigration_court"),
    ("county", "county_benefits"),
    ("medi_cal", "county_benefits"),
    ("benefits", "county_benefits"),
    ("housing_authority", "housing_authority"),
    ("housing", "housing_authority"),
    ("hud", "housing_authority"),
    ("pha_", "housing_authority"),
    ("section_8", "housing_authority"),
    ("private_landlord", "private_landlord"),
    ("landlord", "private_landlord"),
    ("eviction", "eviction_court"),
    ("unlawful_detainer", "eviction_court"),
    ("hospital", "hospital_provider"),
    ("clinic", "hospital_provider"),
    ("medical_bill", "hospital_provider"),
    ("medical_group", "hospital_provider"),
    ("doctor", "hospital_provider"),
    ("physician", "hospital_provider"),
    ("dental", "hospital_provider"),
    ("dentist", "hospital_provider"),
    ("pharmacy", "hospital_provider"),
    ("urgent_care", "hospital_provider"),
    ("health_center", "hospital_provider"),
    ("health_insurance", "health_insurer"),
    ("health_plan", "health_insurer"),
    ("insurance_", "health_insurer"),
    ("explanation_of_benefits", "health_insurer"),
    ("eob", "health_insurer"),
    ("property_manager", "property_manager"),
    ("property_management", "property_manager"),
    ("medicare", "medicare"),
    ("cms_medicare", "medicare"),
    ("ssa", "ssa"),
    ("social_security", "ssa"),
)


def hint_key(doc_type: str | None) -> str | None:
    """The HINTS key for `doc_type` by prefix, or None."""
    if not doc_type:
        return None
    normalized = doc_type.lower().replace("-", "_").replace(" ", "_")
    for prefix, key in _PREFIXES:
        if normalized.startswith(prefix):
            return key
    return None


def where_to_look(doc_type: str | None) -> Hint:
    """Return the search hint for `doc_type`; unknown types get a generic shallow hint."""
    key = hint_key(doc_type)
    return HINTS[key] if key else DEFAULT_HINT


def guess_doc_type(signals: LegitimacySignals) -> str | None:
    """Pick a hint key from the letterhead and form IDs when no doc_type is given."""
    header = " ".join(filter(None, [signals.letterhead, signals.sub_agency])).lower()
    forms = " ".join(signals.form_ids).upper()
    for key, hint in HINTS.items():
        if any(form in forms for form in hint.known_forms):
            return key
    for key, hint in HINTS.items():
        if any(word in header for word in hint.letterhead_keywords):
            return key
    return None


def purpose_key(hint: Hint, call_purpose: str | None) -> str:
    """The purpose_pages key whose keywords match `call_purpose`, else the default."""
    text = (call_purpose or "").lower()
    for key, page in hint.purpose_pages.items():
        if any(word in text for word in page.keywords):
            return key
    return hint.default_purpose
