"""FastAPI app: webhooks, dashboard API, and every agent as async background tasks."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router as api_router
from app.db.engine import ping
from app.db.schema import create_all
from app.dev.router import router as dev_router
from app.memory.worker import MemoryWorker
from app.memory.worker import real_deps as memory_deps
from app.phone import worker as phone_worker
from app.phone.routes import router as phone_router
from app.relay.webhook import router as whatsapp_router
from app.research.worker import ResearchWorker, close_deps, real_deps
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _show_app_logs() -> None:
    """Print our own INFO lines. Uvicorn sets up only its loggers, so without this
    every `app.*` INFO line (calls queued, listen legs, consent) was dropped and
    only warnings reached the console, with no timestamp."""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)


_show_app_logs()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await create_all()
    settings = get_settings()
    worker: ResearchWorker | None = None
    if settings.research_worker and settings.anthropic_api_key:
        worker = ResearchWorker(real_deps(settings))
        worker.start()
    elif settings.research_worker:
        logger.warning("Research worker not started: ANTHROPIC_API_KEY is not set")
    memory: MemoryWorker | None = None
    if settings.memory_worker and settings.anthropic_api_key:
        memory = MemoryWorker(memory_deps(settings))
        memory.start()
    elif settings.memory_worker:
        logger.warning("Memory worker not started: ANTHROPIC_API_KEY is not set")
    phone: phone_worker.PhoneWorker | None = None
    if settings.phone_worker:
        if missing := phone_worker.missing_settings(settings):
            logger.warning("Phone worker not started: %s not set", ", ".join(missing))
        else:
            phone = phone_worker.PhoneWorker(phone_worker.real_deps(settings))
            phone.start()
    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
            await close_deps(worker.deps)
        if memory is not None:
            await memory.stop()
        if phone is not None:
            await phone.stop()
            await phone_worker.close_deps(phone.deps)


app = FastAPI(title="calhacks", lifespan=lifespan)
app.include_router(whatsapp_router)
app.include_router(api_router)
app.include_router(phone_router)  # Twilio's call status and media stream
app.include_router(dev_router)  # 404s unless DEV_ENDPOINTS=true


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    return {"status": "ok", "postgres": await ping()}
