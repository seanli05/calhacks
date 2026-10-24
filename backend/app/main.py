"""FastAPI app: webhooks, dashboard API, and every agent as async background tasks."""

from fastapi import FastAPI

from app.db.engine import ping

app = FastAPI(title="calhacks")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    return {"status": "ok", "postgres": await ping()}
