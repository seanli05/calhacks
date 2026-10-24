"""Every dashboard route, under `/api` (docs/specs/dashboard-api.md)."""

from fastapi import APIRouter

from app.api import cases, feed, users

router = APIRouter(prefix="/api")
router.include_router(users.router)
router.include_router(cases.router)
router.include_router(feed.router)
