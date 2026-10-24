"""Entry point: `python -m app.phone.playground` from backend/. See `__init__.py`."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.phone.llm import AnthropicLlmClient, LlmClient
from app.phone.playground import render
from app.phone.playground.repl import Options, Repl
from app.phone.playground.replay import recorded_answers, replay, table_lines
from app.phone.playground.script import load, save
from app.phone.playground.tap import TapLlm
from app.phone.runner import RunnerConfig
from app.settings import get_settings

_NO_KEY = """\
ANTHROPIC_API_KEY isn't set. Settings read it from the environment or from .env in
the repo root, which a new worktree doesn't have. Either:
  export ANTHROPIC_API_KEY=...            (this shell only)
  cp ../calhacks/.env .env                (from the worktree root; never commit it)
or run without Claude: python -m app.phone.playground --fake"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play the phone line; watch the agent."
    )
    parser.add_argument("--fake", action="store_true", help="no Claude calls")
    parser.add_argument("--replay", type=Path, help="run a saved script and check it")
    parser.add_argument(
        "--rerecord",
        action="store_true",
        help="with --replay: save the run's model answers back into the script",
    )
    parser.add_argument("--goal", help="override the brief's call goal")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--hold-limit-s", type=float, default=None, help="end hold after this long"
    )
    args = parser.parse_args()

    inner: LlmClient | None = None
    if not args.fake:
        if not get_settings().anthropic_api_key:
            sys.exit(_NO_KEY)
        inner = AnthropicLlmClient()
    # The steps already show what the runner's warnings say; --verbose adds them.
    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        format="      %(levelname)s %(message)s",
    )
    config = RunnerConfig(hold_limit_s=args.hold_limit_s)

    if args.replay:
        sys.exit(
            asyncio.run(_replay(args.replay, inner, args.goal, config, args.rerecord))
        )
    try:
        asyncio.run(
            Repl(
                Options(
                    inner=inner, goal=args.goal, verbose=args.verbose, config=config
                )
            ).run()
        )
    except KeyboardInterrupt:
        print()


async def _replay(
    path: Path,
    inner: LlmClient | None,
    goal: str | None,
    config: RunnerConfig,
    rerecord: bool,
) -> int:
    script = load(path)
    if goal:
        script.goal = goal
    if inner is None:
        answers = recorded_answers(script)
        llm = TapLlm(None, cassette=answers, cassette_until=len(script.steps))
    else:
        llm = TapLlm(inner)
    mode = "recorded answers" if inner is None else "real Claude"
    print(
        render.bold(f"replay {path.name}") + render.dim(f" · {mode} · {script.about}")
    )
    rows, session = await replay(script, llm, config=config)
    render.print_lines(table_lines(rows))
    if rerecord and inner is not None:
        # Expectations stay as written; only the recorded answers are new.
        save(session.to_script(script.about), path)
        print(render.dim(f"saved this run's model answers to {path}"))
    return 0 if all(row.passed for row in rows) else 1


if __name__ == "__main__":
    main()
