"""Run the research passes alone: `python -m research.cli {fast,deep,eval}`."""

import argparse
import asyncio
from pathlib import Path


async def run_fast(pages: list[Path], county: str | None) -> None:
    """Print R1 and latency for the given page files."""
    raise NotImplementedError


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

    from research import deep_pass
    from research.fetch_tool import (
        WEB_FIXTURES,
        RecordingTransport,
        replay_resolver,
        replay_transport,
        system_resolver,
    )
    from research.models import LegitimacySignals
    from research.sim.settings import ResearchSettings
    from research.verify_cache import VerifyCache

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


async def run_eval(fixtures_dir: Path) -> None:
    """Print a pass/fail table against each fixture's expected.json, with p50/p95 latency."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="research.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    fast = sub.add_parser("fast", help="run the fast pass on page images or PDFs")
    fast.add_argument("pages", nargs="+", type=Path)
    fast.add_argument("--county")

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

    eval_ = sub.add_parser("eval", help="score the fast pass against fixtures")
    eval_.add_argument("--fixtures", default=Path("fixtures/letters"), type=Path)

    args = parser.parse_args(argv)
    if args.command == "fast":
        asyncio.run(run_fast(args.pages, args.county))
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
        asyncio.run(run_eval(args.fixtures))


if __name__ == "__main__":
    main()
