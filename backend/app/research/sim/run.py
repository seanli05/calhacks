# SIM: replace with the real orchestrator and job worker when persons 1 and 2 land them
"""Solo run of the research flow: upload -> research_fast -> research_deep -> R2 + brief.

Plays the orchestrator (mints IDs, inserts the document, queues H1, answers a
needs_user_input question) and runs a tiny job-runner loop over the real
handlers. `--fake` swaps in canned passes so no API key or real images are needed.
"""

import argparse
import asyncio
import base64
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import httpx
from pydantic import ValidationError

from app.research.deep_pass import LogFn
from app.research.fake import FAKE_URL, fake_deep_findings, fake_fast_pass_output
from app.research.jobs import (
    ResearchDeps,
    handle_research_deep,
    handle_research_fast,
    handle_research_question,
)
from app.research.models import (
    R1,
    DeepFindings,
    FastPassOutput,
    LegitimacySignals,
    QuestionAnswer,
    QuestionSource,
    ResearchDeepPayload,
    ResearchFastPayload,
)
from app.research.preprocess import ContentBlock, UnsupportedMedia
from app.research.sim.memory import InMemoryStore
from app.research.sim.settings import ResearchSettings
from app.research.sim.store import Document, DocumentPage, Job
from app.research.verify_cache import SEED_CACHE_DIR, VerifyCache

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".heic": "image/heic",
}

# SIM: the real job worker claims rows from Postgres instead of this table.
HANDLERS = {
    "research_fast": handle_research_fast,
    "research_deep": handle_research_deep,
    "research_question": handle_research_question,
}

NOT_MERGED = (
    "The real passes aren't merged yet (Tracks A/B), so this hit NotImplementedError. "
    "Run with --fake for now."
)


# --- Fake passes for --fake and tests ---


async def fake_to_blocks(data: bytes, content_type: str) -> list[ContentBlock]:
    """Pass-through: wraps the bytes as a block without decoding them."""
    encoded = base64.b64encode(data).decode()
    if content_type == "application/pdf":
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": encoded,
                },
            }
        ]
    if content_type in ("image/jpeg", "image/png", "image/webp"):
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": encoded,
                },  # type: ignore[typeddict-item]
            }
        ]
    raise UnsupportedMedia("Please send the letter as a JPG or PNG photo, or a PDF.")


async def fake_fast_pass(
    blocks: list[ContentBlock], *, case_id: str, **_: Any
) -> FastPassOutput:
    return fake_fast_pass_output(case_id)


async def fake_deep_pass(
    signals: LegitimacySignals,
    call_purpose: str | None,
    county: str | None,
    *,
    log: LogFn | None = None,
    **_: Any,
) -> DeepFindings:
    findings = fake_deep_findings()
    if log:
        url = findings.trust_chain[0]
        await log(
            "research.search",
            "Searched for the issuer's official site",
            {"query_count": 1},
        )
        await log("research.fetch", "Fetched the official contact page", {"url": url})
        await log(
            "research.check",
            "Official phone found on a trusted page",
            {"check": "phone_on_page", "passed": True},
        )
    return findings


async def fake_answer_question(
    question_en: str, *, log: LogFn | None = None, **_: Any
) -> QuestionAnswer:
    if log:
        await log("research.search", "Searched the web", {})
        await log("research.fetch", "Fetched the official page", {"url": FAKE_URL})
    return QuestionAnswer(
        status="answered",
        answer_en="Fake answer: bring the notice and photo ID to the interview.",
        sources=[QuestionSource(url=FAKE_URL, quote="Bring this notice.")],
    )


def fake_deps() -> ResearchDeps:
    settings = ResearchSettings(
        _env_file=None,  # type: ignore[call-arg]
        model_default="fake",
        model_deep="fake",
        anthropic_api_key="fake",
    )
    return ResearchDeps(
        settings=settings,
        fast_pass_fn=fake_fast_pass,
        deep_pass_fn=fake_deep_pass,
        to_blocks_fn=fake_to_blocks,
        question_fn=fake_answer_question,
    )


# --- Job runner and orchestrator driver ---


async def run_jobs(store: InMemoryStore, deps: ResearchDeps) -> None:
    """Run queued research_* jobs until none are left. Other job types stay queued."""
    while (job := store.next_queued(HANDLERS)) is not None:
        await HANDLERS[job.type](job, store, deps)


def expand_pages(inputs: list[Path]) -> list[Path]:
    pages: list[Path] = []
    for path in inputs:
        if path.is_dir():
            pages += sorted(
                p for p in path.iterdir() if p.suffix.lower() in CONTENT_TYPES
            )
        else:
            pages.append(path)
    return pages


def load_page(path: Path) -> DocumentPage:
    """Read a page file; a missing file becomes an empty page (fine for --fake)."""
    content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    data = path.read_bytes() if path.is_file() else b""
    return DocumentPage(content_type=content_type, data=data)


async def simulate(
    store: InMemoryStore,
    deps: ResearchDeps,
    pages: list[Path],
    answers: dict[str, str],
    ask: Callable[[str], dict[str, str]],
) -> None:
    user_id, case_id, doc_id = (
        f"{p}_{uuid.uuid4().hex[:12]}" for p in ("user", "case", "doc")
    )
    # One document holds every page, in order (C20).
    await store.insert_document(
        Document(
            document_id=doc_id, user_id=user_id, pages=[load_page(p) for p in pages]
        )
    )
    h1 = ResearchFastPayload(
        case_id=case_id, user_id=user_id, document_ids=[doc_id], user_language="es"
    )
    fast_id = await store.create_job(
        "research_fast", h1.model_dump(mode="json"), case_id
    )
    await run_jobs(store, deps)

    fast = store.jobs[fast_id]
    if fast.status != "done" or fast.result is None:
        return
    r1 = R1.model_validate(fast.result)
    if r1.status == "needs_better_image":
        print(f"\nOrchestrator would ask for a new photo. Tip: {r1.image_issue}")
    elif r1.status == "needs_user_input":
        print(f"\nOrchestrator asks the user: {r1.question_en}")
        deep = ResearchDeepPayload(
            case_id=case_id,
            user_id=user_id,
            document_ids=[doc_id],
            answers=answers or ask(r1.question_en or ""),
        )
        await store.create_job("research_deep", deep.model_dump(mode="json"), case_id)
        await run_jobs(store, deps)


def ask_terminal(question: str) -> dict[str, str]:
    raw = input("Answer as key=value (e.g. county=Alameda): ").strip()
    key, sep, value = raw.partition("=")
    return {key.strip(): value.strip()} if sep else {"answer": raw}


# --- Report ---


def mask(value: str) -> str:
    return f"**** ({len(value)} chars)"


def job_summary(job: Job) -> str:
    if job.status == "failed":
        return f"error: {job.error}"
    if job.type not in HANDLERS:
        return "left queued for its own worker (not simulated)"
    if job.result is None:
        return ""
    if job.type == "research_fast":
        return f"R1 status={job.result['status']} doc_type={job.result.get('doc_type')}"
    if job.type == "research_question":
        return (
            f"answer status={job.result['status']} sources={len(job.result['sources'])}"
        )
    v = job.result["verification"]
    return (
        f"R2 verification={v['status']} call_recommended={job.result['call_recommended']} "
        f"brief_id={job.result.get('brief_id')}"
    )


def print_report(store: InMemoryStore) -> None:
    print("\n=== Timeline ===")
    t0 = store.events[0].created_at if store.events else None
    for e in store.events:
        offset = (e.created_at - t0).total_seconds() if t0 else 0.0
        print(f"+{offset:7.3f}s  {e.type:<26} {e.summary_en}  {json.dumps(e.data)}")

    print("\n=== Jobs ===")
    for job in store.jobs.values():
        print(f"{job.job_id}  {job.type:<14} {job.status:<7} {job_summary(job)}")

    print("\n=== Rows written ===")
    for case in store.cases.values():
        r1 = case.r1
        print(
            f"cases: {case.case_id} status={r1.status} doc_type={r1.doc_type} "
            f"issuer={r1.issuer} deadline={r1.deadline} urgency={r1.urgency} "
            f"documents={case.document_ids} call_purpose={case.call_purpose!r}"
        )
    for (case_id, field), value in store.case_refs.items():
        print(f"case_refs: {case_id} <ref:{field}> = {mask(value)}")
    for ver_id, (case_id, v) in store.verifications.items():
        print(
            f"verifications: {ver_id} case={case_id} status={v.status} official_phone={v.official_phone}"
        )
        for s in v.signals:
            print(f"    signal {s.signal}: {s.state}")
    for brief in store.case_briefs.values():
        print(f"case_briefs: {brief.brief_id}")
        print(json.dumps(brief.model_dump(mode="json"), indent=2))


def dump_state(store: InMemoryStore) -> dict[str, Any]:
    return {
        "documents": [
            {
                "document_id": d.document_id,
                "user_id": d.user_id,
                "pages": [
                    {"content_type": p.content_type, "bytes": len(p.data)}
                    for p in d.pages
                ],
            }
            for d in store.documents.values()
        ],
        "cases": [c.model_dump(mode="json") for c in store.cases.values()],
        "case_refs": [
            {"case_id": case_id, "field": field, "value": mask(value)}
            for (case_id, field), value in store.case_refs.items()
        ],
        "verifications": [
            {"ver_id": ver_id, "case_id": case_id, **v.model_dump(mode="json")}
            for ver_id, (case_id, v) in store.verifications.items()
        ],
        "case_briefs": [b.model_dump(mode="json") for b in store.case_briefs.values()],
        "jobs": [j.model_dump(mode="json") for j in store.jobs.values()],
        "events": [e.model_dump(mode="json") for e in store.events],
    }


# --- CLI ---


def parse_answers(pairs: list[str], county: str | None) -> dict[str, str]:
    answers = {k: v for k, _, v in (pair.partition("=") for pair in pairs)}
    if county:
        answers["county"] = county
    return answers


async def run(args: argparse.Namespace) -> int:
    pages = expand_pages(args.pages)
    if not pages:
        print("No page files found.")
        return 2
    answers = parse_answers(args.answer, args.county)
    store = InMemoryStore()

    if args.fake:
        deps = fake_deps()
        await simulate(store, deps, pages, answers, ask_terminal)
    else:
        try:
            settings = ResearchSettings()  # type: ignore[call-arg]
        except ValidationError:
            print(
                "Missing settings: set MODEL_DEFAULT, MODEL_DEEP and ANTHROPIC_API_KEY, or use --fake."
            )
            return 2
        async with (
            anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value()
            ) as client,
            httpx.AsyncClient(timeout=10.0) as http,
        ):
            deps = ResearchDeps(
                settings=settings,
                anthropic=client,
                http=http,
                seed=VerifyCache(SEED_CACHE_DIR),
            )
            try:
                await simulate(store, deps, pages, answers, ask_terminal)
            except NotImplementedError:
                print(f"\n{NOT_MERGED}")

    print_report(store)
    if args.json_out:
        args.json_out.write_text(json.dumps(dump_state(store), indent=2))
        print(f"\nWrote {args.json_out}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m research.sim")
    parser.add_argument(
        "pages", nargs="+", type=Path, help="page files or a fixture directory"
    )
    parser.add_argument("--fake", action="store_true", help="canned passes, no API key")
    parser.add_argument(
        "--county", help="answer for a county question (same as --answer county=X)"
    )
    parser.add_argument("--answer", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--json-out", type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args(argv))))
