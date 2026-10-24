"""Writes owned by the orchestrator: users, media, documents."""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.contracts.common import DocumentId, LanguageCode, MediaId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.tables import utcnow


async def get_or_create_user(whatsapp_number: str) -> tables.User:
    """Safe when two webhooks race for the same new number."""
    new_user = tables.User(whatsapp_number=whatsapp_number)
    async with session() as db:
        await db.execute(
            insert(tables.User)
            .values(**new_user.model_dump())
            .on_conflict_do_nothing(index_elements=["whatsapp_number"])
        )
        await db.commit()
        query = select(tables.User).where(
            tables.User.whatsapp_number == whatsapp_number
        )
        return (await db.execute(query)).scalar_one()


async def set_language(user_id: UserId, language: LanguageCode) -> tables.User:
    async with session() as db:
        user = await must_get(db, tables.User, user_id)
        user.language = language
        await db.commit()
        return user


async def save_media(
    user_id: UserId,
    content_type: str,
    data: bytes,
    twilio_media_url: str | None = None,
) -> tables.Media:
    media = tables.Media(
        user_id=user_id,
        content_type=content_type,
        data=data,
        twilio_media_url=twilio_media_url,
    )
    async with session() as db:
        db.add(media)
        await db.commit()
        return media


def _pages(media_ids: Sequence[MediaId]) -> list[dict[str, str]]:
    added_at = utcnow().isoformat()
    return [{"media_id": media_id, "added_at": added_at} for media_id in media_ids]


async def create_document(
    user_id: UserId, media_ids: Sequence[MediaId]
) -> tables.Document:
    document = tables.Document(user_id=user_id, pages=_pages(media_ids))
    async with session() as db:
        db.add(document)
        await db.commit()
        return document


async def add_pages(
    document_id: DocumentId, media_ids: Sequence[MediaId]
) -> tables.Document:
    """Append page images to a letter, in order (C20)."""
    async with session() as db:
        document = await must_get(db, tables.Document, document_id)
        # A new list, so SQLAlchemy sees the JSON column change.
        document.pages = [*document.pages, *_pages(media_ids)]
        await db.commit()
        return document
