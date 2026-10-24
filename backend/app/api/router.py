"""Every dashboard route, under `/api` (docs/specs/dashboard-api.md)."""

from fastapi import APIRouter

from app.api import users

router = APIRouter(prefix="/api")
router.include_router(users.router)
