"""Deterministic checks the verdict rests on. Pure functions, no I/O."""

import re
from collections.abc import Sequence
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

import phonenumbers
from bs4 import BeautifulSoup

from app.contracts import (
    SignalResult,
    VerificationStatus,
)
from app.research.fetch_tool import FetchedPage, is_gov, registered_domain

DomainTrust = Literal["anchor", "linked_from_anchor", "untrusted"]

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")


def _to_e164(raw: str) -> str | None:
    try:
        number = phonenumbers.parse(raw, "US")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def normalize_phone(raw: str) -> str | None:
    """Any common US formatting -> E.164, or None if it isn't a valid number."""
    return _to_e164(raw)


def phone_on_page(phone: str, html: str) -> bool:
    """True if the E.164 `phone` appears in the page in any common US formatting.

    Checks tel: hrefs and the visible text, read both with and without spaces
    between tags so a number split across tags still matches.
    """
    target = _to_e164(phone)
    if target is None:
        return False
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("tel:") and _to_e164(href[4:]) == target:
            return True
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for separator in (" ", ""):
        text = soup.get_text(separator).translate(_DASHES).replace("\xa0", " ")
        for match in phonenumbers.PhoneNumberMatcher(text, "US"):
            if (
                phonenumbers.format_number(
                    match.number, phonenumbers.PhoneNumberFormat.E164
                )
                == target
            ):
                return True
    return False


def host_in(url_or_host: str, domains: Sequence[str]) -> bool:
    """True if the host is one of `domains` or a subdomain of one."""
    host = urlsplit(url_or_host).hostname if "//" in url_or_host else url_or_host
    host = (host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def domain_trust(url: str, fetched: Sequence[FetchedPage]) -> DomainTrust:
    """Classify `url`'s domain.

    Any .gov is an anchor. A non-.gov domain is trusted only if a real
    `<a href>` on a fetched anchor page links to it.
    """
    if is_gov(url):
        return "anchor"
    domain = registered_domain(url)
    if not domain:
        return "untrusted"
    for page in fetched:
        if not is_gov(page.final_url):
            continue
        for link in page.links:
            if link.startswith("http") and registered_domain(link) == domain:
                return "linked_from_anchor"
    return "untrusted"


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def lookalike(domain: str, anchors: Sequence[str]) -> SignalResult | None:
    """Whether `domain` imitates one of the `anchors`; None if it doesn't.

    An anchor's name on a non-.gov domain (uscis-gov.com) is a conflict. A .gov
    domain one or two edits away (uscls.gov) is uncertain: it may be a misread
    photo, so it never counts as a conflict on its own.
    """
    registered = registered_domain(domain)
    label = registered.split(".")[0]
    for anchor in anchors:
        if registered == anchor:
            return None
        name = anchor.split(".")[0]
        # Short names sit close to many real domains (hud.gov / ed.gov).
        max_distance = 2 if len(name) >= 5 else 1
        distance = _edit_distance(registered, anchor)
        imitates_name = (
            name in re.split(r"[-_]", label)
            or _edit_distance(label, name) <= max_distance
        )
        if not is_gov(registered) and imitates_name:
            return SignalResult(
                signal="url_domains",
                state="conflict",
                evidence=[f"{registered} imitates {anchor} but is not a .gov domain"],
            )
        if distance <= max_distance:
            return SignalResult(
                signal="url_domains",
                state="uncertain",
                evidence=[
                    f"{registered} is {distance} character(s) away from {anchor}; "
                    + "it may be misread, check the letter"
                ],
            )
    return None


def deadline_sane(deadline: date, today: date, max_days: int = 120) -> bool:
    """True if the deadline is not before `today` and within `max_days`."""
    return 0 <= (deadline - today).days <= max_days


def decide_verdict(
    signals: Sequence[SignalResult], red_flags: Sequence[str], issuer_verified: bool
) -> VerificationStatus:
    """Any red flag or conflict -> suspicious; issuer verified and 2+ matches -> verified; else unknown."""
    if red_flags or any(s.state == "conflict" for s in signals):
        return "suspicious"
    other_matches = sum(
        1 for s in signals if s.state == "match" and s.signal != "issuer"
    )
    if issuer_verified and other_matches >= 2:
        return "verified"
    return "unknown"


def case_number_shape(description: str | None) -> tuple[int, int] | None:
    """Parse "3 letters + 10 digits" or a template like "XXX##########" into (letters, digits)."""
    if not description:
        return None
    text = description.lower()
    letters = re.search(r"(\d+)\s*letters?", text)
    digits = re.search(r"(\d+)\s*(?:digits?|numbers?)", text)
    if letters or digits:
        return (
            int(letters.group(1)) if letters else 0,
            int(digits.group(1)) if digits else 0,
        )
    template = re.fullmatch(r"([a-z]*)([0-9#]+)", text.replace("-", "").strip())
    if template:
        return len(template.group(1)), len(template.group(2))
    return None


def form_number(raw: str) -> str | None:
    """`Form I-797C (Rev. 01/01/24)` -> `I-797C`."""
    match = re.search(r"\b([A-Z]{1,4})-?(\d{2,4}[A-Z]?)\b", raw.upper())
    return f"{match.group(1)}-{match.group(2)}" if match else None


def edition_date(raw: str, today: date) -> date | None:
    """`I-797C (edition 10/13/21)` -> 2021-10-13. None if missing, not a real date, or in the future."""
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b", raw)
    if not match:
        return None
    month, day, year = (int(g) for g in match.groups())
    if year < 100:
        year += 2000
    try:
        edition = date(year, month, day)
    except ValueError:
        return None
    return edition if edition <= today else None


def text_of(html: str) -> str:
    """Visible text, whitespace collapsed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def form_on_page(form: str, html: str) -> bool:
    """True if form number `form` (e.g. I-797C) appears in the page text."""
    prefix, _, number = form.partition("-")
    pattern = rf"(?<![A-Za-z0-9]){re.escape(prefix)}[-‐‑– ]?{re.escape(number)}(?![A-Za-z0-9])"
    return re.search(pattern, text_of(html), re.IGNORECASE) is not None


_ADDRESS_ABBREVIATIONS = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "boulevard": "blvd",
    "drive": "dr",
    "suite": "ste",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "parkway": "pkwy",
    "lane": "ln",
}


def _address_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [_ADDRESS_ABBREVIATIONS.get(t, t) for t in tokens]


def address_on_page(address: str, html: str, threshold: float = 0.75) -> bool:
    """Fuzzy match: every number in the address and most of its words appear on the page."""
    wanted = _address_tokens(address)
    if not wanted:
        return False
    present = set(_address_tokens(text_of(html)))
    if any(t.isdigit() and t not in present for t in wanted):
        return False
    return sum(t in present for t in wanted) / len(wanted) >= threshold


def name_on_page(name: str, html: str) -> bool:
    """Case- and whitespace-insensitive substring match of an agency name."""
    needle = " ".join(name.lower().replace("&", "and").split())
    haystack = text_of(html).lower().replace("&", "and")
    return bool(needle) and needle in haystack


def _heading_level(tag_name: str | None) -> int | None:
    match = re.fullmatch(r"h([1-6])", tag_name or "")
    return int(match.group(1)) if match else None


def registry_entry(html: str, name: str, require: str | None = None) -> str | None:
    """HTML of the entry for `name` on a list page with one heading per entry.

    The entry runs from the first heading containing `name` (as whole words) to
    the next heading of the same or a higher level; with `require`, the first
    such entry that also contains it. None if no entry qualifies, so nothing
    from another entry on the page can be attributed to `name`.
    """
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if not words_in(name, heading.get_text(" ")):
            continue
        level = _heading_level(heading.name)
        parts = [str(heading)]
        for sibling in heading.find_next_siblings():
            sibling_level = _heading_level(sibling.name)
            if sibling_level is not None and sibling_level <= level:
                break
            parts.append(str(sibling))
        entry = "".join(parts)
        if require is None or words_in(require, text_of(entry)):
            return entry
    return None


def _normalized(text: str) -> str:
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", text.lower().replace("&", "and")).split()
    )


def words_in(needle: str, text: str) -> bool:
    """True if `needle` appears in `text` as whole words, ignoring case, spacing
    and punctuation ("Court of California, County of X" matches "... | County of X")."""
    needle = _normalized(needle)
    pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return bool(needle) and re.search(pattern, _normalized(text)) is not None


def text_entry(
    html: str, name: str, start: str, require: str | None = None
) -> list[str] | None:
    """Lines of the entry naming `name` on a plain-text list (e.g. a PDF) where
    each entry begins on a line matching the `start` regex; with `require`, the
    first such entry that also contains it. None if no entry qualifies."""
    lines = BeautifulSoup(html, "html.parser").get_text().splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(start, line)]
    for begin, end in zip(starts, [*starts[1:], len(lines)], strict=False):
        entry = lines[begin:end]
        text = " ".join(entry)
        if words_in(name, text) and (require is None or words_in(require, text)):
            return entry
    return None
