"""Run the research passes alone: `python -m research.cli {fast,deep,eval}`."""

import argparse
import asyncio
from pathlib import Path


async def run_fast(pages: list[Path], county: str | None) -> None:
    """Print R1 and latency for the given page files."""
    raise NotImplementedError


async def run_deep(signals_path: Path, county: str | None) -> None:
    """Print R2, the research log, and the trust chain for a signals JSON file."""
    raise NotImplementedError


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

    eval_ = sub.add_parser("eval", help="score the fast pass against fixtures")
    eval_.add_argument("--fixtures", default=Path("fixtures/letters"), type=Path)

    args = parser.parse_args(argv)
    if args.command == "fast":
        asyncio.run(run_fast(args.pages, args.county))
    elif args.command == "deep":
        asyncio.run(run_deep(args.signals, args.county))
    else:
        asyncio.run(run_eval(args.fixtures))


if __name__ == "__main__":
    main()
