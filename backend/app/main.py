"""FastAPI app: webhooks, dashboard API, and every agent as async background tasks."""

from fastapi import FastAPI

app = FastAPI(title="calhacks")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
