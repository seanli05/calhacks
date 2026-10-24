# SIM: replace with the verifications table via DB helpers when person 1 lands it
"""Last good verification per (issuer domain, purpose), with the page snapshot.

A demo fallback for when the live web fails. The snapshot is re-checked by code
on every use, so a cached number is never returned unchecked.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from research.fetch_tool import FetchedPage

DEFAULT_CACHE_DIR = Path("fixtures/web/verify_cache")


class CachedVerification(BaseModel):
    issuer_domain: str
    purpose: str
    official_phone: str
    official_phone_purpose: str | None = None
    source_url: str
    trust_chain: list[str]
    fetched_at: datetime
    pages: list[FetchedPage]
    """Snapshots of the source page and every page in the trust chain."""


class VerifyCache:
    def __init__(self, directory: Path = DEFAULT_CACHE_DIR) -> None:
        self._directory = directory

    def _path(self, issuer_domain: str, purpose: str) -> Path:
        key = hashlib.sha256(f"{issuer_domain}|{purpose}".encode()).hexdigest()[:16]
        return self._directory / f"{issuer_domain}_{key}.json"

    def save(self, entry: CachedVerification) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._path(entry.issuer_domain, entry.purpose).write_text(
            entry.model_dump_json(indent=1)
        )

    def load(self, issuer_domain: str, purpose: str) -> CachedVerification | None:
        path = self._path(issuer_domain, purpose)
        if not path.exists():
            return None
        return CachedVerification.model_validate(json.loads(path.read_text()))
