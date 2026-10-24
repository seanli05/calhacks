"""Deep pass: legitimacy check and official-number lookup on the web.

The model only discovers. Every conclusion is decided by code against pages our
fetch tool fetched: the official number is accepted only if `phone_on_page`
finds it on a trusted page from the issuer's own domain (rule 2, C32).
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import anthropic
import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from research import checks
from research.deep_prompts import DEEP_SYSTEM, FETCH_PAGE_TOOL, SUBMIT_FINDINGS_TOOL
from research.fetch_tool import (
    FetchedPage,
    FetchRefused,
    Resolver,
    fetch_page,
    is_gov,
    page_text_for_model,
    registered_domain,
    system_resolver,
)
from research.hints import (
    BLOCKED_DOMAINS,
    SECONDARY_LINE_WORDS,
    Hint,
    guess_doc_type,
    purpose_key,
    where_to_look,
)
from research.models import (
    AlternativeContact,
    DeepFindings,
    LegitimacySignals,
    SignalResult,
    Verification,
)
from research.scam_rules import scam_red_flags
from research.verify_cache import CachedVerification, VerifyCache

LogFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]
"""(event_type, summary_en, data) for research.search / research.fetch / research.check."""

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 12
MAX_SEARCHES = 6
MAX_FETCHES = 8
MAX_TOKENS = 16_000
DISCOVERY_TIMEOUT_S = 150.0
"""Below the caller's 180 s so the cache fallback still has time to run."""
FALLBACK_BETA = "server-side-fallback-2026-07-01"
BLOCK_STATUSES = (401, 403, 429)
MAX_BLOCKS_PER_DOMAIN = 2
"""After this many bot-wall responses from a domain, stop fetching it."""


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


class _Discovery(BaseModel):
    pages: list[FetchedPage] = []
    submission: Submission | None = None
    failures: list[str] = []
    blocked: dict[str, int] = {}
    """Registered domain -> count of 401/403/429 responses."""


class RunRecord(BaseModel):
    """What the model claimed and which URLs it fetched; replayed offline with fixtures/web."""

    doc_type: str | None
    call_purpose: str | None
    fetched_urls: list[str]
    submission: Submission | None


async def _log(
    log: LogFn | None, event: str, summary: str, data: dict[str, Any]
) -> None:
    if log is not None:
        await log(event, summary, data)


def _same_url(a: str, b: str) -> bool:
    def norm(u: str) -> str:
        return u.split("#")[0].rstrip("/").replace("://www.", "://").lower()

    return norm(a) == norm(b)


def _page_for(url: str | None, pages: list[FetchedPage]) -> FetchedPage | None:
    if not url:
        return None
    for page in pages:
        if _same_url(url, page.url) or _same_url(url, page.final_url):
            return page
    return None


# --- Code checks that need no model ---


async def _early_checks(
    signals: LegitimacySignals, hint: Hint, log: LogFn | None
) -> list[str]:
    """Run the offline checks, log each one, and return the scam red flags."""
    red_flags = scam_red_flags(signals, hint)
    await _log(
        log,
        "research.check",
        f"Scam rules: {len(red_flags)} red flag(s)",
        {"check": "scam_rules", "red_flags": red_flags},
    )
    for result in _offline_signals(signals, hint, []):
        await _log(
            log,
            "research.check",
            f"{result.signal}: {result.state}",
            {
                "check": result.signal,
                "state": result.state,
                "evidence": result.evidence,
            },
        )
    return red_flags


def _offline_signals(
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
        domain = registered_domain(target)
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
    forms = [f for f in (checks.form_number(raw) for raw in signals.form_ids) if f]
    if not forms:
        return SignalResult(
            signal="form_id",
            state="not_found",
            evidence=["No form number on the letter"],
        )
    anchor_pages = [p for p in pages if is_gov(p.final_url)]
    matched: list[str] = []
    evidence: list[str] = []
    uncertain = False
    for form in forms:
        page = next(
            (p for p in anchor_pages if checks.form_on_page(form, p.html)), None
        )
        if page is not None:
            matched.append(form)
            evidence.append(page.final_url)
        elif hint.known_forms and form not in hint.known_forms:
            uncertain = True
            evidence.append(f"{form} is not a form this issuer is known to send")
        else:
            evidence.append(f"{form} was not found on a fetched official page")
    if uncertain:
        state = "uncertain"
    elif matched:
        state = "match"
    else:
        state = "not_found"
    return SignalResult(signal="form_id", state=state, evidence=evidence)


# --- Discovery loop ---


def _user_prompt(
    signals: LegitimacySignals,
    hint: Hint,
    purpose: str,
    call_purpose: str | None,
    county: str | None,
) -> str:
    page = hint.purpose_pages.get(purpose)
    hint_view = {
        "issuer": hint.issuer_short,
        "official_domains": hint.issuer_domains or "discover the issuer's own site",
        "start_from": hint.anchor_domains,
        "fallback_directory": hint.directory_domains
        or "none: only the issuer's own site is accepted",
        "look_for": hint.look_for,
        "page_for_this_purpose": page.page_kind if page else hint.look_for,
        "search_terms": [
            t.format(county=county or "", issuer=signals.letterhead or "")
            for t in hint.search_terms
        ],
    }
    return (
        "<signals>\n"
        + signals.model_dump_json(indent=1, exclude_none=True)
        + "\n</signals>\n<hint>\n"
        + json.dumps(hint_view, indent=1)
        + f"\n</hint>\n<call_purpose>{call_purpose or 'general questions about this letter'}"
        + f"</call_purpose>\n<county>{county or 'unknown'}</county>\n\n"
        "Find the issuer's official site and the official phone number for this purpose, "
        "fetch the pages that show them, then call submit_findings."
    )


async def _discover(
    discovery: _Discovery,
    *,
    signals: LegitimacySignals,
    hint: Hint,
    purpose: str,
    call_purpose: str | None,
    county: str | None,
    client: AsyncAnthropic,
    model: str,
    http: httpx.AsyncClient,
    resolve: Resolver,
    log: LogFn | None,
    max_iterations: int,
) -> None:
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": MAX_SEARCHES,
            "blocked_domains": list(BLOCKED_DOMAINS),
        },
        FETCH_PAGE_TOOL,
        SUBMIT_FINDINGS_TOOL,
    ]
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": _user_prompt(signals, hint, purpose, call_purpose, county),
        }
    ]
    fetches = 0
    nudged = False
    seen_searches: set[str] = set()
    related = list(dict.fromkeys([*hint.issuer_domains, *hint.anchor_domains]))

    for _ in range(max_iterations):
        response = await client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=DEEP_SYSTEM,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if (
                block.type == "server_tool_use"
                and block.name == "web_search"
                and block.id not in seen_searches
            ):
                seen_searches.add(block.id)
                query = str(block.input.get("query", ""))
                await _log(
                    log, "research.search", f"Searched: {query}", {"query": query}
                )
            elif block.type == "web_search_tool_result" and not isinstance(
                block.content, list
            ):
                code = getattr(block.content, "error_code", "unknown")
                discovery.failures.append(f"web search error: {code}")
                await _log(
                    log, "research.search", f"Search failed: {code}", {"error": code}
                )

        stop = response.stop_reason
        if stop == "refusal":
            category = getattr(response.stop_details, "category", None)
            discovery.failures.append(f"the model declined (category: {category})")
            await _log(
                log,
                "research.check",
                "Discovery stopped: model declined",
                {"check": "discovery", "stop_reason": stop, "category": category},
            )
            return
        if stop == "max_tokens":
            discovery.failures.append("the model ran out of output tokens")
            await _log(
                log,
                "research.check",
                "Discovery stopped: max_tokens",
                {"check": "discovery", "stop_reason": stop},
            )
            return
        if stop == "pause_turn":
            continue  # resend as-is; the server resumes the paused turn

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            if nudged:
                discovery.failures.append("the model ended without submitting findings")
                return
            nudged = True
            messages.append(
                {
                    "role": "user",
                    "content": "Call submit_findings now with what you found.",
                }
            )
            continue

        results: list[dict[str, Any]] = []
        for block in tool_uses:
            if block.name == "submit_findings":
                try:
                    discovery.submission = Submission.model_validate(block.input)
                    results.append(_tool_result(block.id, "Received."))
                    # Model text is unverified: it goes to the log, never the result.
                    await _log(
                        log,
                        "research.check",
                        "Model submitted findings (unverified until checked)",
                        {
                            "check": "submission",
                            "issuer_official_domain": discovery.submission.issuer_official_domain,
                            "phone_source_url": discovery.submission.phone_source_url,
                            "notes": discovery.submission.notes,
                        },
                    )
                except ValidationError as exc:
                    results.append(
                        _tool_result(block.id, f"Invalid: {exc}", error=True)
                    )
            elif block.name == "fetch_page":
                if fetches >= MAX_FETCHES:
                    results.append(
                        _tool_result(
                            block.id,
                            "Fetch limit reached. Call submit_findings now.",
                            error=True,
                        )
                    )
                    continue
                url = str(block.input.get("url", ""))
                domain = registered_domain(url)
                if discovery.blocked.get(domain, 0) >= MAX_BLOCKS_PER_DOMAIN:
                    results.append(
                        _tool_result(
                            block.id,
                            f"Not fetched: {domain} blocks automated fetches. "
                            "Do not retry it. Only the official directory named in "
                            "the hint can stand in for the issuer's own site.",
                            error=True,
                        )
                    )
                    continue
                fetches += 1
                text, ok = await _run_fetch(
                    url,
                    discovery=discovery,
                    http=http,
                    resolve=resolve,
                    related=related,
                    log=log,
                )
                results.append(_tool_result(block.id, text, error=not ok))
            else:
                results.append(
                    _tool_result(block.id, f"Unknown tool {block.name}", error=True)
                )
        messages.append({"role": "user", "content": results})
        if discovery.submission is not None:
            return

    discovery.failures.append(f"discovery stopped after {max_iterations} turns")


def _tool_result(tool_use_id: str, text: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": text,
        "is_error": error,
    }


async def _run_fetch(
    url: str,
    *,
    discovery: _Discovery,
    http: httpx.AsyncClient,
    resolve: Resolver,
    related: list[str],
    log: LogFn | None,
) -> tuple[str, bool]:
    try:
        page = await fetch_page(url, http=http, resolve=resolve)
    except FetchRefused as exc:
        await _log(
            log, "research.fetch", f"Refused {url}", {"url": url, "refused": str(exc)}
        )
        return f"Refused: {exc}", False
    except (httpx.HTTPError, TimeoutError) as exc:
        reason = str(exc) or type(exc).__name__
        discovery.failures.append(f"fetch failed for {url}: {reason}")
        await _log(
            log, "research.fetch", f"Fetch failed {url}", {"url": url, "error": reason}
        )
        return f"Fetch failed: {reason}", False
    discovery.pages.append(page)
    await _log(
        log,
        "research.fetch",
        f"Fetched {page.final_url} ({page.status_code})",
        {"url": url, "final_url": page.final_url, "status": page.status_code},
    )
    if page.status_code in BLOCK_STATUSES:
        domain = registered_domain(page.final_url)
        discovery.blocked[domain] = discovery.blocked.get(domain, 0) + 1
        if discovery.blocked[domain] == 1:
            discovery.failures.append(
                f"{domain} blocked our automated fetch (HTTP {page.status_code}), "
                "so nothing on it could be confirmed"
            )
    elif page.status_code >= 400:
        discovery.failures.append(f"{page.final_url} returned HTTP {page.status_code}")
    return page_text_for_model(page, related), page.status_code < 400


# --- Code verification of the model's claims ---


def _issuer_domains(hint: Hint, submission: Submission | None) -> list[str]:
    if hint.issuer_domains:
        return hint.issuer_domains
    if submission and submission.issuer_official_domain:
        domain = registered_domain(submission.issuer_official_domain.strip().lower())
        return [domain] if domain else []
    return []


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


def _issuer_site_unavailable(
    discovery: _Discovery, ok_pages: list[FetchedPage], issuer_domains: list[str]
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
) -> tuple[str | None, FetchedPage | None, str]:
    """(E.164, source page, reason). The number is None unless every check holds.

    The page must be on the issuer's own domain, or, only when that site is
    unavailable, on an official directory's page for this issuer.
    """
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
    page = _page_for(submission.phone_source_url, pages)
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
    on_issuer = bool(issuer_domains) and checks.host_in(page.final_url, issuer_domains)
    via_directory = (
        not on_issuer
        and issuer_unavailable
        and _directory_page_for_issuer(page, hint, issuer_domains)
    )
    if not on_issuer and not via_directory:
        return (
            None,
            None,
            f"{registered_domain(page.final_url)} is not the issuer's domain",
        )
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


def _verify(
    signals: LegitimacySignals,
    hint: Hint,
    call_purpose: str | None,
    red_flags: list[str],
    discovery: _Discovery,
) -> tuple[DeepFindings, FetchedPage | None, list[str]]:
    """Decide the result from fetched pages alone. Returns findings, the source page, issuer domains."""
    # Error and bot-wall pages are not evidence of anything.
    pages = [p for p in discovery.pages if p.status_code < 400]
    submission = discovery.submission
    issuer_domains = _issuer_domains(hint, submission)
    trusted = [
        p for p in pages if checks.domain_trust(p.final_url, pages) != "untrusted"
    ]
    evidence: list[str] = []

    issuer_unavailable = _issuer_site_unavailable(discovery, pages, issuer_domains)
    phone, source, reason = _accept_phone(
        submission,
        discovery.pages,
        issuer_domains,
        hint=hint,
        issuer_unavailable=issuer_unavailable,
    )
    evidence.append(reason)

    # Issuer: its domain is a .gov and the letterhead name appears on it.
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
    issuer_verified = issuer_page is not None
    results = [
        SignalResult(
            signal="issuer",
            state="match" if issuer_verified else "not_found",
            evidence=[issuer_page.final_url]
            if issuer_page
            else ["The letterhead agency was not confirmed on an official .gov page"],
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
            for item in submission.evidence if submission else []:
                if item.signal != "letter_phone_other_owner":
                    continue
                page = _page_for(item.url, trusted)
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
    the issuer's site is unavailable. Any number may end up dialed. Other
    trusted pages keep their URL only.
    """
    contacts: list[AlternativeContact] = []
    for contact in submission.alternative_contacts if submission else []:
        page = _page_for(contact.source_url, pages)
        if page is None or checks.domain_trust(page.final_url, pages) == "untrusted":
            continue
        phone = checks.normalize_phone(contact.phone or "")
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


# --- Cache fallback ---


def _from_cache(
    cache: VerifyCache | None,
    issuer_domains: list[str],
    purpose: str,
) -> tuple[_Discovery, CachedVerification] | None:
    if cache is None:
        return None
    for domain in issuer_domains:
        entry = cache.load(domain, purpose)
        if entry is not None:
            discovery = _Discovery(
                pages=entry.pages,
                submission=Submission(
                    issuer_official_domain=entry.issuer_domain,
                    official_phone=entry.official_phone,
                    phone_source_url=entry.source_url,
                    phone_purpose=entry.official_phone_purpose,
                ),
            )
            return discovery, entry
    return None


async def _apply_cache(
    findings: DeepFindings,
    *,
    cache: VerifyCache | None,
    signals: LegitimacySignals,
    hint: Hint,
    purpose: str,
    call_purpose: str | None,
    red_flags: list[str],
    issuer_domains: list[str],
    log: LogFn | None,
) -> DeepFindings:
    """Re-run every check against the cached snapshot. Returns `findings` unchanged on a miss."""
    cached = _from_cache(cache, issuer_domains, purpose)
    if cached is None:
        return findings
    discovery, entry = cached
    recheck, source, _ = _verify(signals, hint, call_purpose, red_flags, discovery)
    if source is None:
        await _log(
            log,
            "research.check",
            "Cached snapshot failed re-check; not used",
            {"check": "verify_cache", "ok": False},
        )
        return findings
    note = (
        f"Verified from {registered_domain(source.final_url)} on "
        + f"{entry.fetched_at.date().isoformat()} "
        "(saved copy; the live check could not finish)"
    )
    await _log(
        log,
        "research.check",
        note,
        {"check": "verify_cache", "ok": True, "source_url": source.final_url},
    )
    recheck.verification.evidence.insert(0, note)
    recheck.verification.evidence.extend(
        e
        for e in findings.verification.evidence
        if e not in recheck.verification.evidence
    )
    return recheck


# --- Entry points ---


async def _offline_findings(
    signals: LegitimacySignals,
    hint: Hint,
    call_purpose: str | None,
    red_flags: list[str],
    *,
    reason: str,
    cache: VerifyCache | None,
    log: LogFn | None,
) -> DeepFindings:
    discovery = _Discovery(failures=[reason])
    findings, _, issuer_domains = _verify(
        signals, hint, call_purpose, red_flags, discovery
    )
    return await _apply_cache(
        findings,
        cache=cache,
        signals=signals,
        hint=hint,
        purpose=purpose_key(hint, call_purpose),
        call_purpose=call_purpose,
        red_flags=red_flags,
        issuer_domains=issuer_domains,
        log=log,
    )


async def run_code_checks(
    signals: LegitimacySignals,
    call_purpose: str | None,
    *,
    doc_type: str | None = None,
    log: LogFn | None = None,
    cache: VerifyCache | None = None,
) -> DeepFindings:
    """Offline checks only (no model, no web). Uses a cached official contact if one re-checks."""
    hint = where_to_look(doc_type or guess_doc_type(signals))
    red_flags = await _early_checks(signals, hint, log)
    return await _offline_findings(
        signals,
        hint,
        call_purpose,
        red_flags,
        reason="Web discovery was skipped (no API key)",
        cache=cache,
        log=log,
    )


async def run_deep_pass(
    signals: LegitimacySignals,
    call_purpose: str | None,
    county: str | None,
    *,
    client: AsyncAnthropic,
    model: str,
    http: httpx.AsyncClient,
    log: LogFn | None = None,
    doc_type: str | None = None,
    cache: VerifyCache | None = None,
    resolve: Resolver = system_resolver,
    discovery_timeout_s: float = DISCOVERY_TIMEOUT_S,
    max_iterations: int = MAX_ITERATIONS,
    run_record: Path | None = None,
) -> DeepFindings:
    """Verify the letter's issuer and find its official number.

    Manual loop with server `web_search` plus client `fetch_page`; resends on
    `pause_turn`. Sees only legitimacy signals, never personal data.
    `official_phone` is set only when `checks.phone_on_page` finds it on a page
    from a trusted domain. Caller enforces the 180 s timeout; discovery stops
    earlier so the cache fallback can still run.
    """
    hint = where_to_look(doc_type or guess_doc_type(signals))
    purpose = purpose_key(hint, call_purpose)
    red_flags = await _early_checks(signals, hint, log)

    if red_flags or hint.depth == "unverifiable":
        # Scam signals or nothing to verify: no web calls.
        reason = (
            "Web discovery was skipped: the letter has scam red flags"
            if red_flags
            else "This kind of letter can't be verified online"
        )
        return await _offline_findings(
            signals,
            hint,
            call_purpose,
            red_flags,
            reason=reason,
            cache=cache,
            log=log,
        )

    discovery = _Discovery()
    try:
        async with asyncio.timeout(discovery_timeout_s):
            await _discover(
                discovery,
                signals=signals,
                hint=hint,
                purpose=purpose,
                call_purpose=call_purpose,
                county=county or signals.county,
                client=client,
                model=model,
                http=http,
                resolve=resolve,
                log=log,
                max_iterations=max_iterations,
            )
    except TimeoutError:
        discovery.failures.append(
            f"Discovery timed out after {discovery_timeout_s:.0f} s"
        )
    except anthropic.APIError as exc:
        logger.warning("deep pass API error: %s", exc)
        discovery.failures.append(f"Model API error: {type(exc).__name__}")

    if run_record is not None:
        run_record.parent.mkdir(parents=True, exist_ok=True)
        run_record.write_text(
            RunRecord(
                doc_type=doc_type,
                call_purpose=call_purpose,
                fetched_urls=[p.url for p in discovery.pages],
                submission=discovery.submission,
            ).model_dump_json(indent=1)
        )
    return await _finish(
        signals,
        hint,
        purpose,
        call_purpose,
        red_flags,
        discovery,
        cache=cache,
        log=log,
    )


async def replay_deep_pass(
    signals: LegitimacySignals,
    record: RunRecord,
    *,
    http: httpx.AsyncClient,
    resolve: Resolver = system_resolver,
    log: LogFn | None = None,
) -> DeepFindings:
    """Re-run a recorded discovery offline: re-fetch the recorded pages through
    `fetch_page` (backed by a replay transport) and re-verify everything by code."""
    hint = where_to_look(record.doc_type or guess_doc_type(signals))
    purpose = purpose_key(hint, record.call_purpose)
    red_flags = await _early_checks(signals, hint, log)
    discovery = _Discovery(submission=record.submission)
    related = list(dict.fromkeys([*hint.issuer_domains, *hint.anchor_domains]))
    for url in record.fetched_urls:
        await _run_fetch(
            url,
            discovery=discovery,
            http=http,
            resolve=resolve,
            related=related,
            log=log,
        )
    return await _finish(
        signals,
        hint,
        purpose,
        record.call_purpose,
        red_flags,
        discovery,
        cache=None,
        log=log,
    )


async def _finish(
    signals: LegitimacySignals,
    hint: Hint,
    purpose: str,
    call_purpose: str | None,
    red_flags: list[str],
    discovery: _Discovery,
    *,
    cache: VerifyCache | None,
    log: LogFn | None,
) -> DeepFindings:
    """Verify by code, log the result, save to or fall back on the cache."""
    findings, source, issuer_domains = _verify(
        signals, hint, call_purpose, red_flags, discovery
    )
    for result in findings.verification.signals:
        await _log(
            log,
            "research.check",
            f"{result.signal}: {result.state}",
            {
                "check": result.signal,
                "state": result.state,
                "evidence": result.evidence,
            },
        )
    await _log(
        log,
        "research.check",
        f"Verdict: {findings.verification.status}",
        {
            "check": "verdict",
            "status": findings.verification.status,
            "official_phone_found": source is not None,
        },
    )

    if source is not None:
        if cache is not None:
            cache.save(
                CachedVerification(
                    issuer_domain=issuer_domains[0]
                    if issuer_domains
                    else registered_domain(source.final_url),
                    purpose=purpose,
                    official_phone=checks.normalize_phone(
                        discovery.submission.official_phone
                    ),
                    official_phone_purpose=findings.official_phone_purpose,
                    source_url=source.final_url,
                    trust_chain=findings.trust_chain,
                    fetched_at=source.fetched_at,
                    pages=[
                        p
                        for p in discovery.pages
                        if checks.domain_trust(p.final_url, discovery.pages)
                        != "untrusted"
                    ],
                )
            )
        return findings

    if discovery.failures:
        return await _apply_cache(
            findings,
            cache=cache,
            signals=signals,
            hint=hint,
            purpose=purpose,
            call_purpose=call_purpose,
            red_flags=red_flags,
            issuer_domains=issuer_domains,
            log=log,
        )
    return findings
