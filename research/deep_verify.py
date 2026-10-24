"""Deep pass, verification half: decide the result by code from fetched pages alone.

The model's submission is only a claim. Every conclusion here is checked against
pages our fetch tool fetched; how a number is accepted depends on the hint's
trust model (gov_issuer, registry_linked, unverifiable_private).
"""

import json
import re
from datetime import date
from html import escape
from typing import Literal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel

from research import checks
from research.fetch_tool import FetchedPage, extract_links, is_gov, registered_domain
from research.hints import SECONDARY_LINE_WORDS, Hint, Registry
from research.models import (
    AlternativeContact,
    DeepFindings,
    LegitimacySignals,
    SignalResult,
    Verification,
)


class _Evidence(BaseModel):
    signal: Literal[
        "issuer",
        "form_id",
        "return_address",
        "letter_phone",
        "letter_phone_other_owner",
        "url_domains",
    ]
    url: str
    note: str


class _Contact(BaseModel):
    name: str
    purpose: str
    phone: str | None
    source_url: str | None


class Submission(BaseModel):
    """What the model claims via submit_findings. Nothing here is trusted yet."""

    issuer_official_domain: str | None = None
    official_phone: str | None = None
    phone_source_url: str | None = None
    phone_label: str | None = None
    phone_purpose: str | None = None
    alternative_contacts: list[_Contact] = []
    evidence: list[_Evidence] = []
    notes: str = ""


class Discovery(BaseModel):
    pages: list[FetchedPage] = []
    submission: Submission | None = None
    failures: list[str] = []
    blocked: dict[str, int] = {}
    """Registered domain -> count of 401/403/429 responses."""


def _same_url(a: str, b: str) -> bool:
    def norm(u: str) -> str:
        return u.split("#")[0].rstrip("/").replace("://www.", "://").lower()

    return norm(a) == norm(b)


def page_for(url: str | None, pages: list[FetchedPage]) -> FetchedPage | None:
    if not url:
        return None
    for page in pages:
        if _same_url(url, page.url) or _same_url(url, page.final_url):
            return page
    return None


# --- Code checks that need no model ---


def offline_signals(
    signals: LegitimacySignals, hint: Hint, pages: list[FetchedPage]
) -> list[SignalResult]:
    return [
        _url_domains_signal(signals, hint, pages, hint.issuer_domains),
        *_case_number_signal(signals, hint),
        _form_signal(signals, hint, pages),
    ]


def _url_domains_signal(
    signals: LegitimacySignals,
    hint: Hint,
    pages: list[FetchedPage],
    issuer_domains: list[str],
) -> SignalResult:
    if not signals.urls:
        return SignalResult(
            signal="url_domains",
            state="not_found",
            evidence=["The letter prints no web address"],
        )
    anchors = list(dict.fromkeys([*issuer_domains, *hint.anchor_domains]))
    states: list[str] = []
    evidence: list[str] = []
    for url in signals.urls:
        target = url if "//" in url else f"https://{url}"
        domain = org_domain(target)
        if issuer_domains and checks.host_in(target, issuer_domains):
            states.append("match")
            evidence.append(f"{domain} is the issuer's official domain")
            continue
        similar = checks.lookalike(target, anchors)
        if similar is not None:
            states.append(similar.state)
            evidence.extend(similar.evidence)
        elif is_gov(target):
            states.append("match")
            evidence.append(f"{domain} is a .gov domain")
        elif checks.domain_trust(target, pages) == "linked_from_anchor":
            states.append("match")
            evidence.append(f"{domain} is linked from an official .gov page")
        elif hint.federal:
            states.append("conflict")
            evidence.append(f"{domain} is not a .gov domain on a federal notice")
        else:
            states.append("not_found")
            evidence.append(f"{domain} could not be tied to an official site")
    evidence = list(dict.fromkeys(evidence))
    for state in ("conflict", "uncertain", "not_found"):
        if state in states:
            return SignalResult(signal="url_domains", state=state, evidence=evidence)
    return SignalResult(signal="url_domains", state="match", evidence=evidence)


def _case_number_signal(signals: LegitimacySignals, hint: Hint) -> list[SignalResult]:
    if hint.case_number_shape is None:
        return []
    expected = hint.case_number_shape
    shape = checks.case_number_shape(signals.case_number_format)
    if shape is None:
        state, note = "not_found", "No case number format was read from the letter"
    elif shape == expected:
        state, note = (
            "match",
            f"{expected[0]} letters + {expected[1]} digits, as expected",
        )
    else:
        state, note = (
            "uncertain",
            f"Read as {shape[0]} letters + {shape[1]} digits; expected "
            + f"{expected[0]} letters + {expected[1]} digits (may be misread)",
        )
    return [SignalResult(signal="case_number_format", state=state, evidence=[note])]


def _form_signal(
    signals: LegitimacySignals, hint: Hint, pages: list[FetchedPage]
) -> SignalResult:
    # One entry per form; the header and footer often print the same one.
    raws_by_form: dict[str, list[str]] = {}
    for raw in signals.form_ids:
        if (form := checks.form_number(raw)) is not None:
            raws_by_form.setdefault(form, []).append(raw)
    if not raws_by_form:
        return SignalResult(
            signal="form_id",
            state="not_found",
            evidence=["No form number on the letter"],
        )
    anchor_pages = [p for p in pages if is_gov(p.final_url)]
    issuer = hint.issuer_short or "issuer"
    today = date.today()
    matched: list[str] = []
    evidence: list[str] = []
    for form, raws in raws_by_form.items():
        # A form off the known list proves nothing either way: ignore it.
        if hint.known_forms and form not in hint.known_forms:
            evidence.append(f"{form} ignored: not on the known {issuer} form list")
            continue
        page = next(
            (p for p in anchor_pages if checks.form_on_page(form, p.html)), None
        )
        editions = [checks.edition_date(raw, today) for raw in raws]
        edition = next((e for e in editions if e), None) if hint.known_forms else None
        if page is not None:
            matched.append(form)
            evidence.append(page.final_url)
        elif edition is not None:
            matched.append(form)
            evidence.append(
                f"{form} (edition {edition.isoformat()}): known {issuer} form (config)"
            )
        else:
            evidence.append(f"{form} was not found on a fetched official page")
    state = "match" if matched else "not_found"
    return SignalResult(signal="form_id", state=state, evidence=evidence)


# --- Code verification of the model's claims ---

_UNVERIFIABLE = "This kind of sender can't be verified from public sources"


def org_domain(url_or_host: str) -> str:
    """The org's own domain: its registered domain, except under a shared state
    suffix such as ca.gov, where every state and county agency shares one
    registered domain and the full host is kept instead. Empty if there is none."""
    raw = url_or_host.strip().lower()
    host = (urlsplit(raw).hostname if "//" in raw else raw.split("/")[0]) or ""
    host = host.rstrip(".").removeprefix("www.")
    domain = registered_domain(host)
    if re.fullmatch(r"[a-z]{2}\.gov", domain):
        return host if host != domain else ""
    return domain


def issuer_domains_for(hint: Hint, submission: Submission | None) -> list[str]:
    if hint.issuer_domains:
        return hint.issuer_domains
    if submission and submission.issuer_official_domain:
        domain = org_domain(submission.issuer_official_domain)
        return [domain] if domain else []
    return []


class RegistryEntry(BaseModel):
    """The letter's org as listed on a fetched registry page."""

    page: FetchedPage
    registry_name: str
    html: str
    phone_html: str | None
    """Where an accepted number must appear: the entry, or only its main-number
    line. None if the registry doesn't list phone numbers."""
    org_domains: list[str]
    """Domains the entry links to, other than the registry's own site."""


def _entry_names(hint: Hint, signals: LegitimacySignals) -> list[str]:
    fields = {field for registry in hint.registries for field in registry.match_fields}
    names: list[str] = []
    if "county" in fields and signals.county:
        county = re.sub(r"\s+county$", "", signals.county.strip(), flags=re.IGNORECASE)
        names.append(f"{county} County")
    if "name" in fields:
        names.extend(n for n in (signals.letterhead, signals.sub_agency) if n)
    return names


def _city(signals: LegitimacySignals) -> str | None:
    """The city in the letter's return address ("..., Oakland, CA 94612")."""
    match = re.search(
        r",\s*([A-Za-z][A-Za-z .'-]*?)\s*,?\s+[A-Z]{2}\s+\d{5}",
        signals.return_address or "",
    )
    return match.group(1).strip() if match else None


def _npi_entry(html: str, names: list[str], city: str | None) -> str | None:
    """An NPI Registry API response's results naming the org (and city), as one
    entry. Results with the same name and city are the same org (departments),
    so all count. Only the practice-location phone is kept: never fax, mailing
    or authorized-official numbers."""
    try:
        data = json.loads(BeautifulSoup(html, "html.parser").get_text())
    except ValueError:
        return None
    lines: list[str] = []
    for result in data.get("results", []) if isinstance(data, dict) else []:
        orgs = [result.get("basic", {}).get("organization_name") or ""]
        orgs += [
            o.get("organization_name") or "" for o in result.get("other_names", [])
        ]
        addresses = result.get("addresses", [])
        cities = " ".join(a.get("city") or "" for a in addresses)
        if not any(checks.words_in(n, " ".join(orgs)) for n in names):
            continue
        if city and not checks.words_in(city, cities):
            continue
        lines.append(" / ".join(o for o in orgs if o))
        lines.append(f"NPI: {result.get('number')}")
        for address in addresses:
            where = ", ".join(
                address.get(k) or "" for k in ("address_1", "city", "state")
            )
            if address.get("address_purpose") == "LOCATION":
                lines.append(f"Practice location: {where}")
                lines.append(
                    f"Practice location phone: {address.get('telephone_number') or ''}"
                )
            else:
                lines.append(f"Mailing address: {where}")
    return f"<pre>{escape(chr(10).join(lines))}</pre>" if lines else None


def _find_entry(
    page: FetchedPage, registry: Registry, names: list[str], city: str | None
) -> str | None:
    """HTML of the first entry on `page` that names one of `names` (and `city`)."""
    if registry.api == "npi":
        return _npi_entry(page.html, names, city)
    for name in names:
        if registry.entry_start is None:
            if (entry := checks.registry_entry(page.html, name, city)) is not None:
                return entry
        elif lines := checks.text_entry(page.html, name, registry.entry_start, city):
            return f"<pre>{escape(chr(10).join(lines))}</pre>"
    return None


def registry_entries(
    signals: LegitimacySignals, hint: Hint, pages: list[FetchedPage]
) -> list[RegistryEntry]:
    """The letter's org's entry on each fetched .gov registry page that lists it.

    With "city" in a registry's match_fields, the entry must also name the city
    of the letter's return address, when the letter has one.
    """
    names = _entry_names(hint, signals)
    city = _city(signals)
    entries: list[RegistryEntry] = []
    for page in pages:
        registry = next(
            (r for r in hint.registries if checks.host_in(page.final_url, [r.domain])),
            None,
        )
        if registry is None or page.status_code >= 400 or not is_gov(page.final_url):
            continue
        needed_city = city if "city" in registry.match_fields else None
        html = _find_entry(page, registry, names, needed_city)
        if html is None:
            continue
        phone_html = html if registry.returns_phone else None
        if phone_html and registry.phone_line:
            lines = BeautifulSoup(html, "html.parser").get_text().splitlines()
            phone_html = escape(
                "\n".join(line for line in lines if re.match(registry.phone_line, line))
            )
        domains = [
            org_domain(link)
            for link in extract_links(html, page.final_url)
            if link.startswith("http") and not checks.host_in(link, [registry.domain])
        ]
        entries.append(
            RegistryEntry(
                page=page,
                registry_name=registry.name,
                html=html,
                phone_html=phone_html,
                org_domains=list(dict.fromkeys(d for d in domains if d)),
            )
        )
    return entries


def _directory_page_for_issuer(
    page: FetchedPage, hint: Hint, issuer_domains: list[str]
) -> bool:
    """True if `page` is an official directory's page about this issuer.

    It must be on a configured .gov directory, name the issuer by one of its
    official names, and link to the issuer's own domain.
    """
    return bool(
        hint.directory_domains
        and hint.issuer_names
        and issuer_domains
        and page.status_code < 400
        and is_gov(page.final_url)
        and checks.host_in(page.final_url, hint.directory_domains)
        and any(checks.name_on_page(n, page.html) for n in hint.issuer_names)
        and any(
            link.startswith("http") and checks.host_in(link, issuer_domains)
            for link in page.links
        )
    )


def issuer_site_unavailable(
    discovery: Discovery, ok_pages: list[FetchedPage], issuer_domains: list[str]
) -> bool:
    """The issuer's own site blocked us or never yielded a page."""
    blocked = any(d in issuer_domains for d in discovery.blocked)
    fetched = any(checks.host_in(p.final_url, issuer_domains) for p in ok_pages)
    return blocked or not fetched


def _accept_phone(
    submission: Submission | None,
    pages: list[FetchedPage],
    issuer_domains: list[str],
    *,
    hint: Hint,
    issuer_unavailable: bool,
    entries: list[RegistryEntry],
) -> tuple[str | None, FetchedPage | None, str]:
    """(E.164, source page, reason). The number is None unless every check holds.

    The page must be on the issuer's own domain, or inside the issuer's own
    entry on a registry page, or, only when the issuer's site is unavailable, on
    an official directory's page for this issuer.
    """
    if hint.trust_model == "unverifiable_private":
        return None, None, f"{_UNVERIFIABLE}, so no number is accepted"
    if submission is None or not submission.official_phone:
        return None, None, "No official number was found"
    phone = checks.normalize_phone(submission.official_phone)
    if phone is None:
        return None, None, "The proposed number is not a valid phone number"
    label = f"{submission.phone_label or ''} {submission.phone_purpose or ''}".lower()
    secondary = [
        w for w in SECONDARY_LINE_WORDS if re.search(rf"\b{re.escape(w)}\b", label)
    ]
    if secondary:
        return (
            None,
            None,
            f"The proposed number is a special-purpose line ({secondary[0]}), not the main line",
        )
    page = page_for(submission.phone_source_url, pages)
    if page is None:
        return None, None, "The proposed number's page was not fetched by our tool"
    if page.status_code >= 400:
        return None, None, f"{page.final_url} returned HTTP {page.status_code}"
    if checks.domain_trust(page.final_url, pages) == "untrusted":
        return (
            None,
            None,
            f"{registered_domain(page.final_url)} is not a trusted domain",
        )
    entry = next((e for e in entries if e.page is page), None)
    if hint.trust_model == "registry_linked":
        return _accept_registry_phone(phone, page, entry, issuer_domains)
    on_issuer = bool(issuer_domains) and checks.host_in(page.final_url, issuer_domains)
    via_directory = (
        not on_issuer
        and issuer_unavailable
        and _directory_page_for_issuer(page, hint, issuer_domains)
    )
    via_registry = entry if not on_issuer and not via_directory else None
    if not on_issuer and not via_directory and via_registry is None:
        return (
            None,
            None,
            f"{registered_domain(page.final_url)} is not the issuer's domain",
        )
    if via_registry is not None:
        if not (
            via_registry.phone_html
            and checks.phone_on_page(phone, via_registry.phone_html)
        ):
            return (
                None,
                None,
                f"The proposed number is not in this office's entry on {page.final_url}",
            )
        reason = (
            f"Official number found in this office's entry on {page.final_url} "
            + f"({via_registry.registry_name})"
        )
        if issuer_unavailable:
            own_site = ", ".join(issuer_domains) or "the office's own site"
            reason += f"; {own_site} could not be fetched directly"
        return phone, page, reason
    if not checks.phone_on_page(phone, page.html):
        return None, None, f"The proposed number does not appear on {page.final_url}"
    if via_directory:
        return (
            phone,
            page,
            f"Official number found on {page.final_url}, the "
            + f"{registered_domain(page.final_url)} federal directory's page for "
            + f"{hint.issuer_short or 'the issuer'}; {', '.join(issuer_domains)} "
            + "could not be fetched directly",
        )
    return phone, page, f"Official number found on {page.final_url}"


def _accept_registry_phone(
    phone: str,
    page: FetchedPage,
    entry: RegistryEntry | None,
    linked_domains: list[str],
) -> tuple[str | None, FetchedPage | None, str]:
    """registry_linked: (a) the number is in the org's own registry entry, or
    (b) it is on a fetched page of a domain that entry links to."""
    if entry is not None:
        if entry.phone_html and checks.phone_on_page(phone, entry.phone_html):
            return (
                phone,
                page,
                f"Official number found in this organization's entry on {page.final_url} "
                + f"({entry.registry_name})",
            )
        return (
            None,
            None,
            f"The proposed number is not this organization's listed number on {page.final_url}",
        )
    if linked_domains and checks.host_in(page.final_url, linked_domains):
        if checks.phone_on_page(phone, page.html):
            return (
                phone,
                page,
                f"Official number found on {page.final_url}, the website the official "
                + "registry lists for this organization",
            )
        return None, None, f"The proposed number does not appear on {page.final_url}"
    return (
        None,
        None,
        f"{registered_domain(page.final_url)} is neither this organization's registry "
        + "entry nor a website that entry links to",
    )


def _trust_chain(source: FetchedPage, pages: list[FetchedPage]) -> list[str]:
    if checks.domain_trust(source.final_url, pages) == "anchor":
        parent = next(
            (
                p
                for p in pages
                if p is not source
                and registered_domain(p.final_url)
                == registered_domain(source.final_url)
                and any(_same_url(link, source.final_url) for link in p.links)
            ),
            None,
        )
        return [parent.final_url, source.final_url] if parent else [source.final_url]
    domain = registered_domain(source.final_url)
    anchor = next(
        p
        for p in pages
        if is_gov(p.final_url)
        and any(
            link.startswith("http") and registered_domain(link) == domain
            for link in p.links
        )
    )
    return [anchor.final_url, source.final_url]


def _gov_issuer_page(
    signals: LegitimacySignals,
    pages: list[FetchedPage],
    hint: Hint,
    issuer_domains: list[str],
    issuer_unavailable: bool,
    entries: list[RegistryEntry],
) -> FetchedPage | None:
    """gov_issuer: a .gov page of the issuer's domain naming the letterhead agency."""
    names = [n for n in (signals.letterhead, signals.sub_agency) if n]
    issuer_page = next(
        (
            p
            for p in pages
            if is_gov(p.final_url)
            and checks.host_in(p.final_url, issuer_domains)
            and any(checks.name_on_page(n, p.html) for n in names)
        ),
        None,
    )
    if issuer_page is None and issuer_unavailable:
        # The issuer's site is unreachable: an official directory naming the
        # issuer and linking to its domain confirms the issuer instead.
        issuer_page = next(
            (p for p in pages if _directory_page_for_issuer(p, hint, issuer_domains)),
            None,
        )
    if issuer_page is None and entries:
        # The state's official list has an entry for this office.
        issuer_page = entries[0].page
    if issuer_page is None and hint.issuer_domain_named:
        issuer_page = _page_naming_issuer(issuer_domains, pages, signals)
    return issuer_page


def _page_naming_issuer(
    domains: list[str], pages: list[FetchedPage], signals: LegitimacySignals
) -> FetchedPage | None:
    """A fetched .gov page on one of `domains` naming the letterhead office, and
    the letter's county when known (so one county's court is not another's)."""
    names = [n for n in (signals.letterhead, signals.sub_agency) if n]
    for page in pages:
        if not (is_gov(page.final_url) and checks.host_in(page.final_url, domains)):
            continue
        text = checks.text_of(page.html)
        if any(checks.words_in(n, text) for n in names) and (
            not signals.county or checks.words_in(signals.county, text)
        ):
            return page
    return None


def _vouched_domains(
    hint: Hint,
    signals: LegitimacySignals,
    domains: list[str],
    entries: list[RegistryEntry],
    pages: list[FetchedPage],
) -> list[str]:
    """The discovered issuer domains that something official vouches for.

    registry_linked: only domains the org's registry entry links to. gov_issuer:
    those, or a .gov with a fetched page naming the letterhead office; for a
    registry hint with no entry fetched, any .gov domain.
    """
    linked = [d for entry in entries for d in entry.org_domains]
    if hint.trust_model == "registry_linked":
        return [d for d in domains if d in linked] or linked
    if entries or hint.issuer_domain_named:
        named = [d for d in domains if _page_naming_issuer([d], pages, signals)]
        return [d for d in domains if d in linked or d in named] or linked
    return [d for d in domains if is_gov(d)]


def verify(
    signals: LegitimacySignals,
    hint: Hint,
    call_purpose: str | None,
    red_flags: list[str],
    discovery: Discovery,
) -> tuple[DeepFindings, FetchedPage | None, list[str]]:
    """Decide the result from fetched pages alone. Returns findings, the source page, issuer domains."""
    # Error and bot-wall pages are not evidence of anything.
    pages = [p for p in discovery.pages if p.status_code < 400]
    submission = discovery.submission
    issuer_domains = issuer_domains_for(hint, submission)
    entries = registry_entries(signals, hint, pages)
    if not hint.issuer_domains and (hint.registries or hint.issuer_domain_named):
        issuer_domains = _vouched_domains(hint, signals, issuer_domains, entries, pages)
    trusted = [
        p for p in pages if checks.domain_trust(p.final_url, pages) != "untrusted"
    ]
    evidence: list[str] = []

    issuer_unavailable = issuer_site_unavailable(discovery, pages, issuer_domains)
    phone, source, reason = _accept_phone(
        submission,
        discovery.pages,
        issuer_domains,
        hint=hint,
        issuer_unavailable=issuer_unavailable,
        entries=entries,
    )
    evidence.append(reason)

    if hint.trust_model == "gov_issuer":
        issuer_page = _gov_issuer_page(
            signals, pages, hint, issuer_domains, issuer_unavailable, entries
        )
        issuer_missing = (
            "The letterhead agency was not confirmed on an official .gov page"
        )
    elif hint.trust_model == "registry_linked":
        # The org's own entry in a government registry vouches for it.
        issuer_page = entries[0].page if entries else None
        issuer_missing = "This organization was not found in the " + " or ".join(
            r.name for r in hint.registries
        )
    else:
        issuer_page = None
        issuer_missing = _UNVERIFIABLE
    issuer_verified = issuer_page is not None
    results = [
        SignalResult(
            signal="issuer",
            state="match" if issuer_verified else "not_found",
            evidence=[issuer_page.final_url] if issuer_page else [issuer_missing],
        ),
        _url_domains_signal(signals, hint, pages, issuer_domains),
        _form_signal(signals, hint, pages),
        *_case_number_signal(signals, hint),
    ]

    if signals.return_address:
        address_page = next(
            (
                p
                for p in trusted
                if checks.address_on_page(signals.return_address, p.html)
            ),
            None,
        )
        results.append(
            SignalResult(
                signal="return_address",
                state="match" if address_page else "not_found",
                evidence=[address_page.final_url]
                if address_page
                else ["The return address was not found on a fetched official page"],
            )
        )

    letter_phone_matches: bool | None = None
    if signals.phones:
        state, phone_evidence = "not_found", []
        for letter_phone in signals.phones:
            if phone and letter_phone.number == phone:
                state, phone_evidence = "match", [source.final_url]
                break
            on_issuer = next(
                (
                    p
                    for p in trusted
                    if checks.host_in(p.final_url, issuer_domains)
                    and checks.phone_on_page(letter_phone.number, p.html)
                ),
                None,
            )
            if on_issuer:
                state, phone_evidence = "match", [on_issuer.final_url]
                break
            listed = next(
                (
                    e
                    for e in entries
                    if checks.phone_on_page(letter_phone.number, e.html)
                ),
                None,
            )
            if listed:
                state = "match"
                phone_evidence = [
                    f"Listed for this office on {listed.page.final_url} ({listed.registry_name})"
                ]
                break
            for item in submission.evidence if submission else []:
                if item.signal != "letter_phone_other_owner":
                    continue
                page = page_for(item.url, trusted)
                if (
                    page
                    and not checks.host_in(page.final_url, issuer_domains)
                    and checks.phone_on_page(letter_phone.number, page.html)
                ):
                    state = "conflict"
                    phone_evidence = [
                        f"The letter's number appears on {page.final_url}, "
                        + "which is not the issuer's site"
                    ]
        results.append(
            SignalResult(
                signal="letter_phone",
                state=state,
                evidence=phone_evidence
                or ["The letter's number was not found on an official page"],
            )
        )
        letter_phone_matches = {"match": True, "conflict": False}.get(state)
    else:
        results.append(
            SignalResult(
                signal="letter_phone",
                state="not_found",
                evidence=["The letter prints no phone number"],
            )
        )

    status = checks.decide_verdict(results, red_flags, issuer_verified)
    for result in results:
        if result.state == "conflict":
            evidence.extend(result.evidence)
    evidence.extend(discovery.failures)

    issuer_name = hint.issuer_short or signals.letterhead or "Issuing agency"
    purpose_text = (submission.phone_purpose if submission else None) or (
        submission.phone_label if submission else None
    )
    alternatives = _verified_alternatives(
        submission,
        pages,
        issuer_domains,
        hint=hint,
        issuer_unavailable=issuer_unavailable,
    )
    if phone and status != "verified":
        alternatives.insert(
            0,
            AlternativeContact(
                name=f"{issuer_name} official line",
                purpose=purpose_text or "Official contact",
                phone=phone,
                url=source.final_url,
            ),
        )
    if not phone or hint.depth == "unverifiable":
        alternatives.extend(
            AlternativeContact(name=name, purpose=purpose)
            for name, purpose in hint.alternatives
        )

    findings = DeepFindings(
        verification=Verification(
            status=status,
            official_phone=phone if status == "verified" else None,
            letter_phone_matches=letter_phone_matches,
            evidence=evidence,
            red_flags=red_flags,
            signals=results,
        ),
        official_phone_purpose=purpose_text if phone else None,
        alternative_contacts=alternatives,
        trust_chain=_trust_chain(source, pages) if source else [],
        call_goal_en=_call_goal(call_purpose),
    )
    return findings, source, issuer_domains


def _verified_alternatives(
    submission: Submission | None,
    pages: list[FetchedPage],
    issuer_domains: list[str],
    *,
    hint: Hint,
    issuer_unavailable: bool,
) -> list[AlternativeContact]:
    """Model-suggested contacts, keeping only what code can confirm.

    A phone gets the same source bar as official_phone: a fetched page on the
    issuer's own domain, or the configured directory's page for the issuer when
    the issuer's site is unavailable. For an unverifiable sender, whose own
    number is never accepted, only a fetched .gov page qualifies. Any number
    may end up dialed. Other trusted pages keep their URL only.
    """
    contacts: list[AlternativeContact] = []
    for contact in submission.alternative_contacts if submission else []:
        page = page_for(contact.source_url, pages)
        if page is None or checks.domain_trust(page.final_url, pages) == "untrusted":
            continue
        phone = checks.normalize_phone(contact.phone or "")
        if hint.trust_model == "unverifiable_private":
            allowed_source = is_gov(page.final_url)
        else:
            allowed_source = checks.host_in(page.final_url, issuer_domains) or (
                issuer_unavailable
                and _directory_page_for_issuer(page, hint, issuer_domains)
            )
        if phone and not (allowed_source and checks.phone_on_page(phone, page.html)):
            phone = None
        contacts.append(
            AlternativeContact(
                name=contact.name,
                purpose=contact.purpose,
                phone=phone,
                url=page.final_url,
            )
        )
    return contacts


def _call_goal(call_purpose: str | None) -> str | None:
    if not call_purpose or not call_purpose.strip():
        return None
    line = " ".join(call_purpose.split())
    return line[:200]
