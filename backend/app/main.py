"""FastAPI app: webhooks, dashboard API, and every agent as async background tasks."""

from fastapi import FastAPI

from app.db.engine import ping
from app.relay.webhook import router as whatsapp_router

app = FastAPI(title="calhacks")
app.include_router(whatsapp_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    return {"status": "ok", "postgres": await ping()}
