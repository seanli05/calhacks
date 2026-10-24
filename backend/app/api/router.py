"""Every dashboard route, under `/api` (docs/specs/dashboard-api.md)."""

from fastapi import APIRouter

from app.api import cases, users

router = APIRouter(prefix="/api")
router.include_router(users.router)
router.include_router(cases.router)
