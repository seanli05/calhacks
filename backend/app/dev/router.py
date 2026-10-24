"""Dev endpoints: `POST /dev/fake-call` starts the fake phone agent for one user (see
fake_call.py); `POST /dev/fake-research` starts the fake research agent (see
fake_research.py); `POST /dev/fake-phone` starts the fake phone worker, which takes
the call jobs the orchestrator queues after a YES (see fake_phone.py).

Off unless DEV_ENDPOINTS=true, and even then only from the machine running the
server: ngrok makes this app public, and ngrok always adds X-Forwarded-For.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.contracts.common import PhoneE164
from app.db import reads
from app.dev.fake_call import run_fake_call
from app.dev.fake_phone import get_fake_phone
from app.dev.fake_research import get_fake_research
from app.orchestrator.call_status import get_call_status
from app.relay.ask_user import get_ask_user
from app.settings import Settings, get_settings

_LOOPBACK = {"127.0.0.1", "::1"}


def _local_dev_only(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    if not settings.dev_endpoints:
        raise HTTPException(status_code=404)
    local = request.client is not None and request.client.host in _LOOPBACK
    if not local or "x-forwarded-for" in request.headers:
        raise HTTPException(status_code=403, detail="Dev endpoints are local only")


router = APIRouter(prefix="/dev", dependencies=[Depends(_local_dev_only)])


class FakeCallRequest(BaseModel):
    number: PhoneE164
    """The user's WhatsApp number in E.164, e.g. +15105550123."""


class FakeWorkerRequest(BaseModel):
    minutes: float = Field(default=30, gt=0, le=240)
    """How long to keep claiming jobs."""


@router.post("/fake-call", status_code=202)
async def fake_call(
    body: FakeCallRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    user = await reads.get_user_by_number(body.number)
    if user is None or user.language is None:
        raise HTTPException(
            status_code=409,
            detail="Message the bot from this number and pick a language first",
        )
    background_tasks.add_task(run_fake_call, user, get_ask_user(), get_call_status())
    return {"status": "started", "user_id": user.id}


@router.post("/fake-research", status_code=202)
async def fake_research(body: FakeWorkerRequest | None = None) -> dict[str, str]:
    body = body or FakeWorkerRequest()
    started = get_fake_research().start(body.minutes * 60)
    return {"status": "started" if started else "already running"}


@router.post("/fake-phone", status_code=202)
async def fake_phone(body: FakeWorkerRequest | None = None) -> dict[str, str]:
    body = body or FakeWorkerRequest()
    started = get_fake_phone().start(body.minutes * 60)
    return {"status": "started" if started else "already running"}
