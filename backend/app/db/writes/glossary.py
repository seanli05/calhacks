"""Writes owned by the glossary worker."""

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.contracts import TrustLevel
from app.contracts.common import LanguageCode
from app.db import tables
from app.db.engine import session


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
