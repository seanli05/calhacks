"""`POST /dev/fake-call`: start the fake phone agent for one user (see fake_call.py).

Off unless DEV_ENDPOINTS=true, and even then only from the machine running the
server: ngrok makes this app public, and ngrok always adds X-Forwarded-For.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.contracts.common import PhoneE164
from app.db import reads
from app.dev.fake_call import run_fake_call
from app.orchestrator.call_status import get_call_status
from app.relay.ask_user import get_ask_user
from app.settings import Settings, get_settings

router = APIRouter(prefix="/dev")

_LOOPBACK = {"127.0.0.1", "::1"}


class FakeCallRequest(BaseModel):
    number: PhoneE164
    """The user's WhatsApp number in E.164, e.g. +15105550123."""


@router.post("/fake-call", status_code=202)
async def fake_call(
    body: FakeCallRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if not settings.dev_endpoints:
        raise HTTPException(status_code=404)
    local = request.client is not None and request.client.host in _LOOPBACK
    if not local or "x-forwarded-for" in request.headers:
        raise HTTPException(status_code=403, detail="Dev endpoints are local only")
    user = await reads.get_user_by_number(body.number)
    if user is None or user.language is None:
        raise HTTPException(
            status_code=409,
            detail="Message the bot from this number and pick a language first",
        )
    background_tasks.add_task(run_fake_call, user, get_ask_user(), get_call_status())
    return {"status": "started", "user_id": user.id}
