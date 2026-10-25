"""Every dashboard route, under `/api` (docs/specs/dashboard-api.md)."""

from fastapi import APIRouter

from app.api import cases, feed, live, memory, suggestions, users

router = APIRouter(prefix="/api")
router.include_router(users.router)
router.include_router(cases.router)
router.include_router(feed.router)
router.include_router(memory.router)
router.include_router(suggestions.router)
router.include_router(live.router)
