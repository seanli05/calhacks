"""Run the research passes alone: `python -m research.cli {fast,deep,ask,eval,seed}`."""

import argparse
import asyncio
import functools
import mimetypes
import sys
import time
from pathlib import Path

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.research.eval_harness import report
from app.research.eval_harness import run_eval as run_eval_fixtures
from app.research.fake import fake_fast_pass_output
from app.research.fast_pass import FastPassError, run_fast_pass
from app.research.models import FastPassOutput
from app.research.preprocess import ContentBlock, UnsupportedMedia, to_content_blocks
from app.research.sim.settings import ResearchSettings

LETTER_FIXTURES = (
    Path(__file__).resolve().parents[2] / "tests/fixtures/research/letters"
)

FAST_TIMEOUT_S = 45.0
CLI_CASE_ID = "case_cli"
NO_KEY_MESSAGE = (
    "No API key: set ANTHROPIC_API_KEY, MODEL_DEFAULT and MODEL_DEEP in .env "
    "(see .env.example)."
)


def _load_settings() -> ResearchSettings | None:
    """Settings with a non-empty API key, or None."""
    try:
        settings = ResearchSettings()
    except ValidationError:
        return None
    if not settings.anthropic_api_key.get_secret_value().strip():
        return None
    return settings


def _client(settings: ResearchSettings) -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())


async def _read_pages(pages: list[Path]) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for page in pages:
        content_type = mimetypes.guess_type(page.name)[0] or "application/octet-stream"
        blocks.extend(await to_content_blocks(page.read_bytes(), content_type))
    return blocks


def _print_output(out: FastPassOutput, latency_s: float) -> None:
    print("== R1")
    print(out.r1.model_dump_json(indent=2))
    print("\n== Legitimacy signals")
    print(out.signals.model_dump_json(indent=2))
    print(f"\n== call_purpose: {out.call_purpose}")
    print(f"== unknown_terms: {', '.join(out.unknown_terms) or '-'}")
    print("== sensitive_values (masked)")
    for sv in out.sensitive_values:
        print(f"  {sv.ref:<28} {sv.field:<20} [{len(sv.value)} chars hidden]")
    if not out.sensitive_values:
        print("  -")
    print(f"\n== latency: {latency_s:.1f}s")


async def run_fast(
    pages: list[Path],
    county: str | None,
    signals_out: Path | None = None,
    fake: bool = False,
) -> int:
    """Print R1, signals, call purpose, unknown terms, masked sensitive values and latency."""
    started = time.monotonic()
    if fake:
        out = fake_fast_pass_output(CLI_CASE_ID)
    else:
        settings = _load_settings()
        if settings is None:
            print(
                NO_KEY_MESSAGE + " Or pass --fake for canned output.", file=sys.stderr
            )
            return 2
        try:
            blocks = await _read_pages(pages)
        except (OSError, UnsupportedMedia) as e:
            print(f"Can't read pages: {e}", file=sys.stderr)
            return 1
        try:
            out = await asyncio.wait_for(
                run_fast_pass(
                    blocks,
                    case_id=CLI_CASE_ID,
                    client=_client(settings),
                    model=settings.model_default,
                    profile_county=county,
                ),
                FAST_TIMEOUT_S,
            )
        except TimeoutError:
            print(f"Fast pass timed out after {FAST_TIMEOUT_S:.0f}s", file=sys.stderr)
            return 1
        except FastPassError as e:
            print(f"Fast pass failed: {e}", file=sys.stderr)
            return 1
    _print_output(out, time.monotonic() - started)
    if signals_out:
        signals_out.write_text(out.signals.model_dump_json(indent=2) + "\n")
        print(f"== signals written to {signals_out}")
    return 0


async def run_deep(
    signals_path: Path,
    county: str | None,
    *,
    doc_type: str | None = None,
    purpose: str | None = None,
    mode: str | None = None,
) -> None:
    """Print R2, the research log, and the trust chain for a signals JSON file.

    The file is either bare LegitimacySignals or `{"signals": ..., "doc_type": ...,
    "call_purpose": ...}`. `mode` is "record" (save pages and the run to
    fixtures/web) or "replay" (no network, no model).
    """
    import json
    import time

    import httpx
    from anthropic import AsyncAnthropic
    from pydantic import ValidationError

    from app.research import deep_pass
    from app.research.fetch_tool import (
        WEB_FIXTURES,
        RecordingTransport,
        replay_resolver,
        replay_transport,
        system_resolver,
    )
    from app.research.models import LegitimacySignals
    from app.research.sim.settings import ResearchSettings
    from app.research.verify_cache import SEED_CACHE_DIR, VerifyCache

    raw = json.loads(signals_path.read_text())
    signals = LegitimacySignals.model_validate(raw.get("signals", raw))
    doc_type = doc_type or raw.get("doc_type")
    purpose = purpose or raw.get("call_purpose")
    run_path = WEB_FIXTURES / "runs" / f"{signals_path.stem}.json"
    started = time.monotonic()

    async def log(event: str, summary: str, data: dict) -> None:
        print(f"[{time.monotonic() - started:6.1f}s] {event:<16} {summary}", flush=True)

    async with asyncio.timeout(180):
        if mode == "replay":
            if not run_path.exists():
                raise SystemExit(f"No recorded run at {run_path}; record one first.")
            record = deep_pass.RunRecord.model_validate_json(run_path.read_text())
            async with httpx.AsyncClient(transport=replay_transport()) as http:
                findings = await deep_pass.replay_deep_pass(
                    signals, record, http=http, resolve=replay_resolver, log=log
                )
        else:
            try:
                settings = ResearchSettings()
            except ValidationError:
                settings = None
            if settings is None or not settings.anthropic_api_key.get_secret_value():
                print(
                    "No ANTHROPIC_API_KEY: running code checks only; discovery loop skipped."
                )
                findings = await deep_pass.run_code_checks(
                    signals, purpose, doc_type=doc_type, log=log, cache=VerifyCache()
                )
            else:
                transport = RecordingTransport() if mode == "record" else None
                async with (
                    httpx.AsyncClient(transport=transport) as http,
                    AsyncAnthropic(
                        api_key=settings.anthropic_api_key.get_secret_value()
                    ) as client,
                ):
                    findings = await deep_pass.run_deep_pass(
                        signals,
                        purpose,
                        county,
                        client=client,
                        model=settings.model_deep,
                        http=http,
                        log=log,
                        doc_type=doc_type,
                        cache=VerifyCache(),
                        seed=VerifyCache(SEED_CACHE_DIR),
                        resolve=system_resolver,
                        run_record=run_path if mode == "record" else None,
                    )

    v = findings.verification
    print(f"\nVerdict: {v.status.upper()}   ({time.monotonic() - started:.1f}s)")
    print("\nSignals:")
    for s in v.signals:
        print(f"  {s.signal:<20} {s.state:<10} {'; '.join(s.evidence)}")
    if v.red_flags:
        print("\nRed flags:")
        for flag in v.red_flags:
            print(f"  - {flag}")
    print(f"\nOfficial phone: {v.official_phone or 'none'}")
    if findings.official_phone_purpose:
        print(f"  purpose: {findings.official_phone_purpose}")
    print(f"Letter phone matches: {v.letter_phone_matches}")
    if findings.trust_chain:
        print("Trust chain: " + " -> ".join(findings.trust_chain))
    if findings.alternative_contacts:
        print("\nAlternative contacts:")
        for c in findings.alternative_contacts:
            print(f"  - {c.name} ({c.purpose}) {c.phone or ''} {c.url or ''}".rstrip())
    print("\nEvidence:")
    for e in v.evidence:
        print(f"  - {e}")
    if findings.call_goal_en:
        print(f"\nCall goal: {findings.call_goal_en}")


async def run_eval(fixtures_dir: Path, runs: int = 1) -> int:
    """Print a pass/fail table against each fixture's expected.json, with p50/p95 latency."""
    settings = _load_settings()
    if settings is None:
        print(NO_KEY_MESSAGE, file=sys.stderr)
        return 2
    fast = functools.partial(
        run_fast_pass,
        case_id=CLI_CASE_ID,
        client=_client(settings),
        model=settings.model_default,
    )
    results = await run_eval_fixtures(
        fixtures_dir, fast, runs=runs, timeout_s=FAST_TIMEOUT_S
    )
    table, ok = report(results, runs)
    print(table)
    return 0 if ok else 1


def run_seed(
    html_path: Path, url: str, phone: str, captured: str, purpose: str | None
) -> int:
    """Load a page saved from a browser into the seed cache, after checking the phone is on it."""
    from datetime import UTC, datetime

    from app.research.fetch_tool import registered_domain
    from app.research.hints import DEFAULT_HINT, HINTS
    from app.research.verify_cache import SEED_CACHE_DIR, VerifyCache, seed_entry

    # The deep pass looks seeds up by (domain, purpose key); a wrong key is never found.
    valid = sorted(
        {DEFAULT_HINT.default_purpose}
        | {key for hint in HINTS.values() for key in hint.purpose_pages}
    )
    if purpose is None:
        domain = registered_domain(url)
        defaults = [
            h.default_purpose for h in HINTS.values() if domain in h.issuer_domains
        ]
        if not defaults:
            print(f"Pass --purpose for {domain} (one of: {', '.join(valid)})")
            return 2
        purpose = defaults[0]
    if purpose not in valid:
        print(f"Unknown purpose {purpose!r} (one of: {', '.join(valid)})")
        return 2
    captured_at = datetime.fromisoformat(captured).replace(tzinfo=UTC)
    try:
        entry = seed_entry(
            html_path.read_text(errors="replace"), url, phone, captured_at, purpose
        )
    except ValueError as exc:
        print(f"Not seeded: {exc}")
        return 1
    VerifyCache(SEED_CACHE_DIR).save(entry)
    print(
        f"Seeded {entry.issuer_domain} ({purpose}) from {url}, captured {captured}: "
        f"{entry.official_phone} found on the page"
    )
    return 0


async def run_ask(question: str) -> int:
    """Answer one process question with the real model and web; print the result and log."""
    import httpx

    from app.research.jobs import QUESTION_TIMEOUT_S
    from app.research.question import answer_question

    settings = _load_settings()
    if settings is None:
        print(NO_KEY_MESSAGE)
        return 2
    started = time.monotonic()

    async def log(event: str, summary: str, data: dict) -> None:
        print(f"[{time.monotonic() - started:6.1f}s] {event:<16} {summary}", flush=True)

    async with _client(settings) as client, httpx.AsyncClient(timeout=10.0) as http:
        try:
            answer = await asyncio.wait_for(
                answer_question(
                    question,
                    client=client,
                    model=settings.model_default,
                    http=http,
                    log=log,
                ),
                QUESTION_TIMEOUT_S,
            )
        except TimeoutError:
            print(
                f"Timed out after {QUESTION_TIMEOUT_S:.0f} s (job result: not_confirmed)"
            )
            return 1
    print(f"\n== {time.monotonic() - started:.1f}s")
    print(answer.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.research.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    fast = sub.add_parser("fast", help="run the fast pass on page images or PDFs")
    fast.add_argument("pages", nargs="+", type=Path)
    fast.add_argument("--county")
    fast.add_argument("--signals-out", type=Path, help="save signals JSON for `deep`")
    fast.add_argument(
        "--fake", action="store_true", help="print canned output, no API call"
    )

    deep = sub.add_parser("deep", help="run the deep pass on a signals JSON file")
    deep.add_argument("--signals", required=True, type=Path)
    deep.add_argument("--county")
    deep.add_argument("--doc-type")
    deep.add_argument("--purpose", help="call purpose in English")
    deep_mode = deep.add_mutually_exclusive_group()
    deep_mode.add_argument(
        "--record", action="store_const", const="record", dest="mode"
    )
    deep_mode.add_argument(
        "--replay", action="store_const", const="replay", dest="mode"
    )

    ask = sub.add_parser("ask", help="answer a general process question (English)")
    ask.add_argument("question")

    eval_ = sub.add_parser("eval", help="score the fast pass against fixtures")
    eval_.add_argument("--fixtures", default=LETTER_FIXTURES, type=Path)
    eval_.add_argument("--runs", default=1, type=int)

    seed = sub.add_parser(
        "seed", help="load a page saved from a browser as an official snapshot"
    )
    seed.add_argument("html", type=Path)
    seed.add_argument("--url", required=True, help="the page's real URL")
    seed.add_argument("--phone", required=True, help="official number on the page")
    seed.add_argument("--captured", required=True, help="date saved, YYYY-MM-DD")
    seed.add_argument(
        "--purpose", help="purpose key; inferred for issuers with a fixed domain"
    )

    args = parser.parse_args(argv)
    if args.command == "seed":
        sys.exit(run_seed(args.html, args.url, args.phone, args.captured, args.purpose))
    if args.command == "ask":
        sys.exit(asyncio.run(run_ask(args.question)))
    if args.command == "fast":
        sys.exit(
            asyncio.run(run_fast(args.pages, args.county, args.signals_out, args.fake))
        )
    elif args.command == "deep":
        asyncio.run(
            run_deep(
                args.signals,
                args.county,
                doc_type=args.doc_type,
                purpose=args.purpose,
                mode=args.mode,
            )
        )
    else:
        sys.exit(asyncio.run(run_eval(args.fixtures, args.runs)))


if __name__ == "__main__":
    main()
