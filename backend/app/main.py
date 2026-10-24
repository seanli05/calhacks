"""FastAPI app: webhooks, dashboard API, and every agent as async background tasks."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router as api_router
from app.db.engine import ping
from app.db.schema import create_all
from app.dev.router import router as dev_router
from app.relay.webhook import router as whatsapp_router
from app.research.worker import ResearchWorker, close_deps, real_deps
from app.settings import get_settings

logger = logging.getLogger(__name__)


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
    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
            await close_deps(worker.deps)


app = FastAPI(title="calhacks", lifespan=lifespan)
app.include_router(whatsapp_router)
app.include_router(api_router)
app.include_router(dev_router)  # 404s unless DEV_ENDPOINTS=true


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    return {"status": "ok", "postgres": await ping()}
