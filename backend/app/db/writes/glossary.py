"""Writes owned by the glossary worker."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.contracts import TrustLevel
from app.contracts.common import LanguageCode
from app.db import tables
from app.db.engine import session

if TYPE_CHECKING:
    from app.glossary.load import GlossaryRow


async def add_term(
    term: str,
    language: LanguageCode,
    translation: str,
    trust_level: TrustLevel,
    source_url: str | None = None,
) -> tables.GlossaryTerm:
    """Add a term, or replace the translation if (term, language) exists."""
    row = tables.GlossaryTerm(
        term=term,
        language=language,
        translation=translation,
        trust_level=trust_level,
        source_url=source_url,
    )
    async with session() as db:
        await db.execute(
            insert(tables.GlossaryTerm)
            .values(**row.model_dump())
            .on_conflict_do_update(
                index_elements=["term", "language"],
                set_={
                    "translation": translation,
                    "trust_level": trust_level,
                    "source_url": source_url,
                },
            )
        )
        await db.commit()
        query = select(tables.GlossaryTerm).where(
            tables.GlossaryTerm.term == term, tables.GlossaryTerm.language == language
        )
        return (await db.execute(query)).scalar_one()


async def add_terms(rows: Sequence["GlossaryRow"]) -> int:
    """`add_term` for many rows in one statement, for loading the preset glossary
    fast (a reset). Returns how many rows were written."""
    if not rows:
        return 0
    values = [
        tables.GlossaryTerm(
            term=row.term,
            language=row.language,
            translation=row.translation,
            trust_level=row.trust_level,
            source_url=row.source_url,
        ).model_dump()
        for row in rows
    ]
    statement = insert(tables.GlossaryTerm).values(values)
    async with session() as db:
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=["term", "language"],
                set_={
                    "translation": statement.excluded.translation,
                    "trust_level": statement.excluded.trust_level,
                    "source_url": statement.excluded.source_url,
                },
            )
        )
        await db.commit()
    return len(rows)
