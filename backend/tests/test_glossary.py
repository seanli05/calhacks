"""The preset glossary (`terms.csv`) and its loader. No database: `add_term` is faked."""

import csv
from pathlib import Path
from typing import Any

import pytest
from app.contracts import TrustLevel
from app.glossary import load
from app.glossary.load import GlossaryError, GlossaryRow

TIER_1 = {"es", "fa", "ne"}
SEED = {"asylum interview": "entrevista de asilo", "interpreter": "intérprete"}
SEED |= {"dependent": "dependiente"}


@pytest.fixture(scope="module")
def rows() -> list[GlossaryRow]:
    return load.read_rows()


def test_every_row_validates(rows: list[GlossaryRow]) -> None:
    assert len(rows) > 200


def test_no_duplicate_term_language(rows: list[GlossaryRow]) -> None:
    keys = [(row.term, row.language) for row in rows]
    assert len(keys) == len(set(keys))


def test_every_core_term_has_tier_1_languages(rows: list[GlossaryRow]) -> None:
    terms = {row.term for row in rows}
    assert 50 <= len(terms) <= 80
    for language in TIER_1:
        have = {row.term for row in rows if row.language == language}
        assert have == terms, f"{language} is missing {sorted(terms - have)}"


def test_trust_levels_are_honest(rows: list[GlossaryRow]) -> None:
    assert all(row.trust_level != TrustLevel.COMMUNITY for row in rows)
    for row in rows:
        if row.trust_level == TrustLevel.OFFICIAL:
            assert row.source_url and row.source_url.startswith("https://")
            assert row.locator, f"{row.term}/{row.language} has no locator"


def test_tier_2_is_official_only(rows: list[GlossaryRow]) -> None:
    tier_2 = [row for row in rows if row.language not in TIER_1]
    assert tier_2
    assert all(row.trust_level == TrustLevel.OFFICIAL for row in tier_2)


def test_seed_terms_keep_their_spelling(rows: list[GlossaryRow]) -> None:
    """The demo brief's `glossary_terms` match glossary rows by exact string."""
    spanish = {row.term: row.translation for row in rows if row.language == "es"}
    for term, translation in SEED.items():
        assert spanish[term] == translation


@pytest.mark.parametrize("language", ["fa", "ne"])
def test_review_sheet_matches_terms(rows: list[GlossaryRow], language: str) -> None:
    sheet_path = Path(load.__file__).with_name(f"review_{language}.csv")
    with sheet_path.open(encoding="utf-8", newline="") as f:
        sheet = list(csv.DictReader(f))
    column = {"fa": "dari", "ne": "nepali"}[language]
    expected = {row.term: row.translation for row in rows if row.language == language}
    assert {entry["term"]: entry[column] for entry in sheet} == expected


def _write_csv(path: Path, lines: list[str]) -> Path:
    header = ",".join(load.COLUMNS)
    path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")
    return path


def test_bad_rows_are_all_listed(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "terms.csv",
        [
            "Asylum,es,asilo,machine,,,",
            "asylum,es,asilo,community,,,",
            "oath,es,juramento,official,,,",
            "oath,spa,juramento,machine,,,",
            "witness,es,,machine,,,",
            "fraud,es,fraude,machine,,,",
            "fraud,es,fraude,machine,,,",
        ],
    )
    with pytest.raises(GlossaryError) as error:
        load.read_rows(path)
    message = str(error.value)
    for line in range(2, 7):
        assert f"line {line} " in message
    assert "line 8: duplicate 'fraud' / es" in message


def test_wrong_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "terms.csv"
    path.write_text("term,language,translation\nasylum,es,asilo\n", encoding="utf-8")
    with pytest.raises(GlossaryError, match="header"):
        load.read_rows(path)


class FakeAddTerm:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture
def add_term(monkeypatch: pytest.MonkeyPatch) -> FakeAddTerm:
    fake = FakeAddTerm()
    monkeypatch.setattr("app.db.writes.glossary.add_term", fake)
    return fake


async def test_load_writes_each_row_once(
    rows: list[GlossaryRow], add_term: FakeAddTerm
) -> None:
    assert await load.load(rows) == len(rows)
    assert len(add_term.calls) == len(rows)
    first = rows[0]
    assert add_term.calls[0] == {
        "term": first.term,
        "language": first.language,
        "translation": first.translation,
        "trust_level": first.trust_level,
        "source_url": first.source_url,
    }
    machine = next(row for row in rows if row.trust_level == TrustLevel.MACHINE)
    call = add_term.calls[rows.index(machine)]
    assert call["source_url"] is None


def test_main_loads_one_language(
    rows: list[GlossaryRow], add_term: FakeAddTerm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load, "get_settings", _fake_settings)
    assert load.main(["--language", "ne"]) == 0
    assert {call["language"] for call in add_term.calls} == {"ne"}
    assert len(add_term.calls) == sum(row.language == "ne" for row in rows)


def test_dry_run_never_touches_the_database(
    add_term: FakeAddTerm, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_settings() -> None:
        raise AssertionError("dry run read the database settings")

    monkeypatch.setattr(load, "get_settings", no_settings)
    assert load.main(["--dry-run"]) == 0
    assert load.main(["--dry-run", "--language", "fa"]) == 0
    assert add_term.calls == []


def test_unknown_language_fails(add_term: FakeAddTerm) -> None:
    assert load.main(["--dry-run", "--language", "xx"]) == 1
    assert add_term.calls == []


class _FakeSettings:
    async_database_url = "postgresql+asyncpg://user@fake-host.invalid/db"


def _fake_settings() -> _FakeSettings:
    return _FakeSettings()
