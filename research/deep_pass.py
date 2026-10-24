"""Deep pass: legitimacy check and official-number lookup on the web.

The model only discovers. Every conclusion is decided by code against pages our
fetch tool fetched: the official number is accepted only if `phone_on_page`
finds it on a trusted page from the issuer's own domain (rule 2, C32). This
module runs discovery and the cache fallbacks; `deep_verify` decides.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anthropic
import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from research import checks
from research.deep_prompts import DEEP_SYSTEM, FETCH_PAGE_TOOL, SUBMIT_FINDINGS_TOOL
from research.deep_verify import (
    Discovery,
    Submission,
    issuer_domains_for,
    issuer_site_unavailable,
    offline_signals,
    page_for,
    registry_entries,
    verify,
)
from research.fetch_tool import (
    MODEL_MAX_LINKS,
    FetchedPage,
    FetchRefused,
    Resolver,
    fetch_page,
    page_text_for_model,
    registered_domain,
    system_resolver,
)
from research.hints import (
    BLOCKED_DOMAINS,
    Hint,
    guess_doc_type,
    purpose_key,
    where_to_look,
)
from research.models import DeepFindings, LegitimacySignals
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
    for result in offline_signals(signals, hint, []):
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
    if hint.trust_model == "unverifiable_private":
        hint_view["goal"] = (
            "This kind of sender can't be verified from public sources, so do not "
            "look for its number. Instead find official .gov help for the person: "
            + "; ".join(name for name, _ in hint.alternatives)
            + ". Give each as an alternative contact, with the fetched .gov page "
            "that shows its number."
        )
    if hint.registries:
        hint_view["official_lists"] = [
            {"name": r.name, "where": r.url or r.domain} for r in hint.registries
        ]
        hint_view["how_lists_vouch"] = (
            "Fetch the official list and find this organization's own entry. A number "
            "counts if it is in that entry, or on a fetched page of the website that "
            "entry links to. Give that website as issuer_official_domain."
        )
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
    discovery: Discovery,
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
                    registry_view=lambda page: _registry_view(page, signals, hint),
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
    discovery: Discovery,
    http: httpx.AsyncClient,
    resolve: Resolver,
    related: list[str],
    log: LogFn | None,
    registry_view: Callable[[FetchedPage], str] | None = None,
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
    text = page_text_for_model(page, related)
    if registry_view is not None:
        text += registry_view(page)
    return text, page.status_code < 400


def _registry_view(page: FetchedPage, signals: LegitimacySignals, hint: Hint) -> str:
    """Extra model text for an official list page: the letter's org's own entry
    (a long list is truncated in the page text) and the list's links out."""
    domains = [r.domain for r in hint.registries]
    if not checks.host_in(page.final_url, domains):
        return ""
    parts = [
        "This organization's entry on the list:\n" + checks.text_of(entry.html)
        for entry in registry_entries(signals, hint, [page])
    ]
    # On an official list, the links out to each listed org are the point.
    outside = [
        link
        for link in page.links
        if link.startswith("http") and not checks.host_in(link, domains)
    ]
    if outside:
        parts.append(
            "Links to other sites on this official list:\n"
            + "\n".join(f"- {link}" for link in outside[:MODEL_MAX_LINKS])
        )
    return "".join(f"\n\n{part}" for part in parts)


# --- Cache fallback ---


def _from_cache(
    cache: VerifyCache | None,
    issuer_domains: list[str],
    purpose: str,
) -> tuple[Discovery, CachedVerification] | None:
    if cache is None:
        return None
    for domain in issuer_domains:
        entry = cache.load(domain, purpose)
        if entry is not None:
            discovery = Discovery(
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
    recheck, source, _ = verify(signals, hint, call_purpose, red_flags, discovery)
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
    discovery = Discovery(failures=[reason])
    findings, _, issuer_domains = verify(
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
    seed: VerifyCache | None = None,
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

    discovery = Discovery()
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
        seed=seed,
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
    discovery = Discovery(submission=record.submission)
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


async def _add_seed_pages(
    seed: VerifyCache | None,
    discovery: Discovery,
    hint: Hint,
    purpose: str,
    log: LogFn | None,
) -> tuple[str, str, list[FetchedPage]] | None:
    """When the issuer's site gave us no usable page, add its saved copy to the pages checked.

    Same condition as the directory fallback. The copy goes through every code
    check like a live page and replaces any error stub for the same URL.
    Returns (domain, capture date, snapshot pages) if used.
    """
    if seed is None:
        return None
    ok_pages = [p for p in discovery.pages if p.status_code < 400]
    issuer_domains = issuer_domains_for(hint, discovery.submission)
    if not issuer_site_unavailable(discovery, ok_pages, issuer_domains):
        return None
    for domain in issuer_domains:
        entry = seed.load(domain, purpose)
        if entry is None:
            continue
        pages = [p for p in entry.pages if p.status_code < 400]
        discovery.pages = [
            p
            for p in discovery.pages
            if page_for(p.url, pages) is None and page_for(p.final_url, pages) is None
        ] + pages
        captured = entry.fetched_at.date().isoformat()
        await _log(
            log,
            "research.check",
            f"Using the saved {domain} snapshot from {captured}",
            {"check": "seed_snapshot", "source_url": entry.source_url},
        )
        return domain, captured, pages
    return None


async def _finish(
    signals: LegitimacySignals,
    hint: Hint,
    purpose: str,
    call_purpose: str | None,
    red_flags: list[str],
    discovery: Discovery,
    *,
    cache: VerifyCache | None,
    log: LogFn | None,
    seed: VerifyCache | None = None,
) -> DeepFindings:
    """Verify by code, log the result, save to or fall back on the cache."""
    used_seed = await _add_seed_pages(seed, discovery, hint, purpose, log)
    findings, source, issuer_domains = verify(
        signals, hint, call_purpose, red_flags, discovery
    )
    if used_seed is not None:
        domain, captured, seed_pages = used_seed
        # "Verified" only when the official number itself came from the snapshot.
        note = (
            f"Verified from {domain} snapshot on {captured}"
            if any(source is p for p in seed_pages)
            else f"Checked against the {domain} snapshot from {captured}"
        )
        findings.verification.evidence.insert(
            0, f"{note} (the live {domain} site could not be fetched)"
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
        # Last good live result first, then a saved snapshot; each is re-checked.
        for fallback in (cache, seed):
            rechecked = await _apply_cache(
                findings,
                cache=fallback,
                signals=signals,
                hint=hint,
                purpose=purpose,
                call_purpose=call_purpose,
                red_flags=red_flags,
                issuer_domains=issuer_domains,
                log=log,
            )
            if rechecked is not findings:
                return rechecked
    return findings
