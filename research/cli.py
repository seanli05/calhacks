"""Run the research passes alone: `python -m research.cli {fast,deep,eval}`."""

import argparse
import asyncio
import functools
import mimetypes
import sys
import time
from pathlib import Path

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from research.eval_harness import report
from research.eval_harness import run_eval as run_eval_fixtures
from research.fake import fake_fast_pass_output
from research.fast_pass import FastPassError, run_fast_pass
from research.models import FastPassOutput
from research.preprocess import ContentBlock, UnsupportedMedia, to_content_blocks
from research.sim.settings import ResearchSettings

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


async def run_deep(signals_path: Path, county: str | None) -> None:
    """Print R2, the research log, and the trust chain for a signals JSON file."""
    raise NotImplementedError


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="research.cli")
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

    eval_ = sub.add_parser("eval", help="score the fast pass against fixtures")
    eval_.add_argument("--fixtures", default=Path("fixtures/letters"), type=Path)
    eval_.add_argument("--runs", default=1, type=int)

    args = parser.parse_args(argv)
    if args.command == "fast":
        sys.exit(
            asyncio.run(run_fast(args.pages, args.county, args.signals_out, args.fake))
        )
    elif args.command == "deep":
        asyncio.run(run_deep(args.signals, args.county))
    else:
        sys.exit(asyncio.run(run_eval(args.fixtures, args.runs)))


if __name__ == "__main__":
    main()
