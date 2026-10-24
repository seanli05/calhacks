"""Answer one general process question from official pages (research_question job).

The question is scrubbed of the case's sensitive values and ID-shaped strings,
asylum-claim questions are declined in code before any model call, and the
model searches and, if needed, reads pages. Code then keeps only sources on a
.gov URL whose quote appears word for word in text we hold for that URL: a
page fetched by us or by web_fetch, or the cited_text of a web_search citation
(uscis.gov often blocks both fetchers). An answer with no surviving source
becomes not_confirmed.
"""

import re
from collections.abc import Iterable
from typing import Any

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from research.deep_pass import FALLBACK_BETA, LogFn, _log, _same_url
from research.deep_prompts import FETCH_PAGE_TOOL
from research.fetch_tool import (
    FetchRefused,
    Resolver,
    fetch_page,
    is_gov,
    page_text_for_model,
    system_resolver,
)
from research.hints import BLOCKED_DOMAINS, ID_SHAPED_PATTERNS
from research.models import R1, QuestionAnswer, QuestionSource, QuestionStatus
from research.question_prompts import QUESTION_SYSTEM, SUBMIT_ANSWER_TOOL

MAX_ITERATIONS = 8
MAX_SEARCHES = 3
MAX_FETCHES = 4
MAX_WEB_FETCHES = 3
MAX_TOKENS = 8_000
EFFORT = "low"
REDACTED = "[redacted]"
MAX_UNCITED_CHARS = 60

# Narrower than fast_pass.ASYLUM_CLAIM_MARKERS: "citizenship" or "religious ID"
# are fine process questions, so only words about the claim itself trip the gate.
CLAIM_MARKERS = (
    "persecut",
    "tortur",
    "fled",
    "why i left",
    "reason for leaving",
    "reasons for leaving",
    "political opinion",
    "social group",
    "my asylum story",
    "my asylum claim",
)

NOT_CONFIRMED_REASON = "No official page confirmed an answer"
ASYLUM_REASON = "Questions about the asylum claim itself are not answered"
RETRY_CITED = (
    "Rejected: none of the quotes appear in text we can check. Reply with the "
    "answer as plain text that cites the .gov search results, with no tool call."
)


class _Submission(BaseModel):
    status: QuestionStatus
    answer_en: str | None = None
    sources: list[QuestionSource] = []


def scrub_question(question: str, sensitive: Iterable[str]) -> str:
    """Replace the case's sensitive values and ID-shaped strings before the model sees them."""
    text = question
    for value in sorted({v for v in sensitive if v}, key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
        text = re.sub(pattern, REDACTED, text, flags=re.IGNORECASE)
    for pattern in ID_SHAPED_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def mentions_asylum_claim(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in CLAIM_MARKERS)


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def letter_context(r1: R1) -> str:
    """What the question model may know about the user's letter: R1's plain
    fields only. R1 never holds sensitive values (they travel as refs)."""
    lines = [
        f"Document type: {r1.doc_type}" if r1.doc_type else "",
        f"Issuer: {r1.issuer}" if r1.issuer else "",
        f"What it asks: {r1.what_is_asked}" if r1.what_is_asked else "",
        f"Deadline: {r1.deadline.isoformat()}" if r1.deadline else "",
        f"Appointment date: {r1.appointment.date.isoformat()}"
        if r1.appointment
        else "",
        *(f"Checklist ({c.kind}): {c.item}" for c in r1.checklist_en),
        f"Explanation: {r1.explanation_en[:1500]}" if r1.explanation_en else "",
    ]
    return "\n".join(line for line in lines if line)


async def answer_question(
    question_en: str,
    *,
    letter: str | None = None,
    sensitive: Iterable[str] = (),
    client: AsyncAnthropic,
    model: str,
    http: httpx.AsyncClient,
    resolve: Resolver = system_resolver,
    log: LogFn | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> QuestionAnswer:
    """Research one question, optionally about the user's letter (`letter_context`).
    The caller enforces the overall time cap."""
    question = scrub_question(question_en, sensitive)
    if mentions_asylum_claim(question):
        await _log(
            log,
            "research.check",
            "Declined: the question is about the asylum claim",
            {"check": "asylum_gate", "passed": False},
        )
        return QuestionAnswer(status="declined_asylum_claim", reason_en=ASYLUM_REASON)

    if letter:
        # Context only: the letter is never a source, answers still need quotes
        # found on official pages fetched here.
        question = (
            "The person is asking about a letter they received. Summary, for "
            "context only (not a source):\n<letter>\n"
            + scrub_question(letter, sensitive)
            + f"\n</letter>\n\n<question>{question}</question>"
        )
    pages: dict[str, str] = {}
    submission = await _ask_model(
        question,
        pages,
        client=client,
        model=model,
        http=http,
        resolve=resolve,
        log=log,
        max_iterations=max_iterations,
    )
    if submission is None:
        return QuestionAnswer(status="not_confirmed", reason_en=NOT_CONFIRMED_REASON)
    return await _verify(submission, pages, log)


async def _verify(
    submission: _Submission, pages: dict[str, str], log: LogFn | None
) -> QuestionAnswer:
    """Keep the model's answer only if a fetched .gov page holds a quoted source."""
    if submission.status != "answered":
        reason = {
            "not_confirmed": NOT_CONFIRMED_REASON,
            "declined_legal_advice": "This asks for legal advice, which we don't give",
            "declined_asylum_claim": ASYLUM_REASON,
            "out_of_scope": "This is not about a government process",
        }[submission.status]
        return QuestionAnswer(status=submission.status, reason_en=reason)

    kept: list[QuestionSource] = []
    for source in submission.sources:
        passed = _confirmed(source, pages)
        await _log(
            log,
            "research.check",
            f"Source {'confirmed' if passed else 'rejected'}: {source.url}",
            {"check": "quote_on_page", "url": source.url, "passed": passed},
        )
        if passed:
            kept.append(source)
    if not kept or not submission.answer_en:
        return QuestionAnswer(status="not_confirmed", reason_en=NOT_CONFIRMED_REASON)
    return QuestionAnswer(
        status="answered", answer_en=submission.answer_en, sources=kept
    )


def _text_answer(content: list[Any]) -> _Submission | None:
    """A plain-text answer whose citations are all .gov search results, or None.

    The quotes are the API's cited_text, so they come from the search index, not
    from the model. Uncited text is allowed only as short connectors ("Yes.").
    """
    texts = [b for b in content if b.type == "text" and b.text.strip()]
    sources: list[QuestionSource] = []
    for block in texts:
        citations = [
            c
            for c in getattr(block, "citations", None) or []
            if c.type == "web_search_result_location"
        ]
        if not citations and len(block.text.strip()) > MAX_UNCITED_CHARS:
            return None
        for c in citations:
            if not is_gov(c.url):
                return None
            source = QuestionSource(url=c.url, quote=c.cited_text)
            if source not in sources:
                sources.append(source)
    if not sources:
        return None
    answer = "".join(b.text for b in texts).strip()
    return _Submission(status="answered", answer_en=answer, sources=sources)


def _confirmed(source: QuestionSource, pages: dict[str, str]) -> bool:
    """True if the quote is on a .gov URL whose text we hold."""
    text = next((t for url, t in pages.items() if _same_url(url, source.url)), None)
    return (
        is_gov(source.url) and text is not None and _norm(source.quote) in _norm(text)
    )


async def _ask_model(
    question: str,
    pages: dict[str, str],
    *,
    client: AsyncAnthropic,
    model: str,
    http: httpx.AsyncClient,
    resolve: Resolver,
    log: LogFn | None,
    max_iterations: int,
) -> _Submission | None:
    """Run the search/read loop. Fills `pages` with every page text the model was shown.

    Uses the basic web tool versions on purpose: the dynamic-filtering ones read
    results inside model-written code, whose output can't serve as evidence, and
    the model then writes no citations.
    """
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_SEARCHES,
            "blocked_domains": list(BLOCKED_DOMAINS),
        },
        {
            "type": "web_fetch_20250910",
            "name": "web_fetch",
            "max_uses": MAX_WEB_FETCHES,
            "blocked_domains": list(BLOCKED_DOMAINS),
        },
        FETCH_PAGE_TOOL,
        SUBMIT_ANSWER_TOOL,
    ]
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    fetches = 0
    nudged = False
    rejected = False

    for _ in range(max_iterations):
        response = await client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=QUESTION_SYSTEM,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        messages.append({"role": "assistant", "content": response.content})
        await _record_server_tools(response.content, pages, log)

        if response.stop_reason in ("refusal", "max_tokens"):
            await _log(
                log,
                "research.check",
                f"Question research stopped: {response.stop_reason}",
                {"check": "question_loop", "stop_reason": response.stop_reason},
            )
            return None
        if response.stop_reason == "pause_turn":
            continue  # resend as-is; the server resumes the paused turn

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text_answer = _text_answer(response.content)
            if text_answer is not None:
                return text_answer
            if nudged:
                return None
            nudged = True
            messages.append(
                {
                    "role": "user",
                    "content": "Call submit_answer now with what you found.",
                }
            )
            continue

        results: list[dict[str, Any]] = []
        submission: _Submission | None = None
        for block in tool_uses:
            if block.name == "submit_answer":
                try:
                    candidate = _Submission.model_validate(block.input)
                except ValidationError as exc:
                    results.append(
                        _tool_result(block.id, f"Invalid: {exc}", error=True)
                    )
                    continue
                if (
                    candidate.status == "answered"
                    and not rejected
                    and not any(_confirmed(s, pages) for s in candidate.sources)
                ):
                    # One retry: search results are only visible to us as citations.
                    rejected = True
                    results.append(_tool_result(block.id, RETRY_CITED, error=True))
                else:
                    submission = candidate
                    results.append(_tool_result(block.id, "Received."))
            elif block.name == "fetch_page":
                if fetches >= MAX_FETCHES:
                    results.append(
                        _tool_result(
                            block.id,
                            "Fetch limit reached. Call submit_answer now.",
                            error=True,
                        )
                    )
                    continue
                fetches += 1
                url = str(block.input.get("url", ""))
                text, ok = await _fetch(url, pages, http=http, resolve=resolve, log=log)
                results.append(_tool_result(block.id, text, error=not ok))
            else:
                results.append(
                    _tool_result(block.id, f"Unknown tool {block.name}", error=True)
                )
        messages.append({"role": "user", "content": results})
        if submission is not None:
            return submission
    return None


async def _record_server_tools(
    content: list[Any], pages: dict[str, str], log: LogFn | None
) -> None:
    """Log server-side tools; keep web_fetch page text and web_search cited text."""
    for block in content:
        if block.type == "text":
            for citation in getattr(block, "citations", None) or []:
                if citation.type != "web_search_result_location":
                    continue
                url = citation.url
                pages[url] = f"{pages.get(url, '')}\n{citation.cited_text}"
                await _log(
                    log,
                    "research.search",
                    f"Cited search result {url}",
                    {"url": url, "via": "search_citation"},
                )
        elif block.type == "server_tool_use" and block.name == "web_search":
            # The query is derived from the user's words, so it stays out of events.
            await _log(log, "research.search", "Searched the web", {})
        elif block.type == "server_tool_use" and block.name == "web_fetch":
            url = str(block.input.get("url", ""))
            await _log(
                log, "research.fetch", f"web_fetch requested {url}", {"url": url}
            )
        elif block.type == "web_fetch_tool_result":
            result = block.content
            if getattr(result, "type", None) != "web_fetch_result":
                code = getattr(result, "error_code", "unknown")
                await _log(
                    log, "research.fetch", f"web_fetch failed: {code}", {"error": code}
                )
                continue
            source = result.content.source
            if source.type != "text":
                continue  # PDFs can't be quote-checked here
            pages[result.url] = source.data
            await _log(
                log,
                "research.fetch",
                f"Fetched {result.url} (web_fetch)",
                {"url": result.url, "via": "web_fetch"},
            )


async def _fetch(
    url: str,
    pages: dict[str, str],
    *,
    http: httpx.AsyncClient,
    resolve: Resolver,
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
        await _log(
            log, "research.fetch", f"Fetch failed {url}", {"url": url, "error": reason}
        )
        return (
            f"Fetch failed for {url}: {reason}. Try web_fetch on the same URL.",
            False,
        )
    await _log(
        log,
        "research.fetch",
        f"Fetched {page.final_url} ({page.status_code})",
        {"url": url, "final_url": page.final_url, "status": page.status_code},
    )
    if page.status_code >= 400:
        blocked = (
            f"HTTP {page.status_code}: the site blocked or failed this fetch of "
            f"{url}. Try web_fetch on the same URL."
        )
        return blocked, False
    text = page_text_for_model(page)
    # Keyed by where the page really came from, so a .gov link that redirects
    # off-site can't be cited as official.
    pages[page.final_url] = text
    return text, True


def _tool_result(tool_use_id: str, text: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": text,
        "is_error": error,
    }
