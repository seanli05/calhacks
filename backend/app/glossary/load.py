"""Load the preset glossary (`terms.csv`) into the `glossary` table.

    python -m app.glossary.load --dry-run              # validate and count; no database
    python -m app.glossary.load                        # write every row
    python -m app.glossary.load --language fa          # write one language only

Run from `backend/`. Each row goes through `writes.glossary.add_term`, which inserts or
replaces by (term, language), so re-running is safe and leaves other rows alone.
The database is shared by the whole team: tell them before a real (non dry-run) load.
A reset (`app.db.reset`) drops the table, so the glossary must be loaded again after it.
"""

import argparse
import asyncio
import csv
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.contracts import TrustLevel
from app.contracts.common import LanguageCode
from app.db.writes import glossary as glossary_writes
from app.settings import get_settings

TERMS_CSV = Path(__file__).with_name("terms.csv")
COLUMNS = ["term", "language", "translation", "trust_level", "source_url", "locator", "note"]


class GlossaryError(ValueError):
    """`terms.csv` has rows that can't be loaded; the message lists every one."""


class GlossaryRow(BaseModel):
    term: str
    language: LanguageCode
    translation: str
    trust_level: TrustLevel
    source_url: str | None = None
    locator: str = ""
    note: str = ""

    @field_validator("term")
    @classmethod
    def _lowercase_term(cls, term: str) -> str:
        """The dashboard matches brief terms by exact lowercase string."""
        if not term.strip() or term != term.strip().lower():
            raise ValueError("term must be non-empty, trimmed, and lowercase")
        return term

    @field_validator("translation")
    @classmethod
    def _has_translation(cls, translation: str) -> str:
        if not translation.strip():
            raise ValueError("translation is empty")
        return translation

    @field_validator("source_url", mode="before")
    @classmethod
    def _blank_url_is_none(cls, url: str | None) -> str | None:
        return url or None

    @model_validator(mode="after")
    def _honest_trust(self) -> "GlossaryRow":
        """Only a human checker may mark a row community; official needs its source."""
        if self.trust_level == TrustLevel.COMMUNITY:
            raise ValueError("community rows come only from a human checker")
        if self.trust_level == TrustLevel.OFFICIAL and not self.source_url:
            raise ValueError("official rows need a source_url")
        return self


def read_rows(path: Path = TERMS_CSV) -> list[GlossaryRow]:
    """Every row of `path`, validated; raises GlossaryError listing all bad rows."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise GlossaryError(f"{path.name}: header must be {','.join(COLUMNS)}")
        raw = list(reader)
    rows: list[GlossaryRow] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for line, values in enumerate(raw, start=2):
        try:
            row = GlossaryRow.model_validate(values)
        except ValidationError as exc:
            reasons = "; ".join(error["msg"] for error in exc.errors())
            problems.append(f"line {line} ({values.get('term')!r}): {reasons}")
            continue
        key = (row.term, row.language)
        if key in seen:
            problems.append(f"line {line}: duplicate {row.term!r} / {row.language}")
        seen.add(key)
        rows.append(row)
    if problems:
        raise GlossaryError(f"{path.name} has bad rows:\n  " + "\n  ".join(problems))
    return rows


def counts(rows: Sequence[GlossaryRow]) -> dict[str, Counter[str]]:
    by_language: dict[str, Counter[str]] = {}
    for row in rows:
        by_language.setdefault(row.language, Counter())[row.trust_level.value] += 1
    return dict(sorted(by_language.items()))


async def load(rows: Sequence[GlossaryRow]) -> int:
    """Write each row; returns how many were written."""
    for row in rows:
        await glossary_writes.add_term(
            term=row.term,
            language=row.language,
            translation=row.translation,
            trust_level=row.trust_level,
            source_url=row.source_url,
        )
    return len(rows)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.glossary.load")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and count; no database"
    )
    parser.add_argument("--language", help="load only this ISO 639-1 code, e.g. fa")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    try:
        rows = read_rows()
    except GlossaryError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.language:
        rows = [row for row in rows if row.language == args.language]
        if not rows:
            print(f"No rows for language {args.language!r}.", file=sys.stderr)
            return 1
    for language, by_trust in counts(rows).items():
        summary = ", ".join(f"{level} {n}" for level, n in sorted(by_trust.items()))
        print(f"{language}: {sum(by_trust.values())} ({summary})")
    print(f"Total: {len(rows)} rows, {len({row.term for row in rows})} terms")
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    host = urlsplit(get_settings().async_database_url).hostname or "?"
    print(f"Writing to {host}")
    written = asyncio.run(load(rows))
    print(f"Done: {written} rows written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
