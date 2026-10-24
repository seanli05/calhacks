"""Demo entry point, public config, the user, their WhatsApp thread, and media."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.common import found
from app.api.models import DemoInfo, Message, PublicConfig, UserInfo
from app.db import reads
from app.settings import Settings, get_settings

router = APIRouter()


@router.get("/demo")
async def demo() -> DemoInfo:
    user = found(await reads.first_user(), "user")
    cases = await reads.list_active_cases(user.id)
    return DemoInfo(user_id=user.id, case_id=cases[0].id if cases else None)


@router.get("/config")
async def config(settings: Annotated[Settings, Depends(get_settings)]) -> PublicConfig:
    code = settings.twilio_sandbox_join_code.strip()
    return PublicConfig(
        whatsapp_number=settings.twilio_whatsapp_from.removeprefix("whatsapp:"),
        sandbox_join_message=f"join {code}" if code else None,
    )


@router.get("/users/{user_id}")
async def user(user_id: str) -> UserInfo:
    row = found(await reads.get_user(user_id), "user")
    return UserInfo(id=row.id, language=row.language)


@router.get("/users/{user_id}/messages")
async def messages(user_id: str) -> list[Message]:
    return [
        Message(
            id=row.id,
            at=row.created_at,
            direction=row.direction,
            sender=row.sender,
            body=row.body_original,
            body_en=row.body_en,
            language=row.language,
            media_ids=row.media_ids,
            case_id=row.case_id,
        )
        for row in await reads.list_messages(user_id)
    ]


@router.get("/media/{media_id}")
async def media(media_id: str) -> Response:
    row = found(await reads.get_media(media_id), "media")
    return Response(content=row.data, media_type=row.content_type)
