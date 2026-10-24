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

from app.research import checks
from app.research.fetch_tool import (
    WEB_FIXTURES,
    FetchedPage,
    extract_links,
    registered_domain,
)

DEFAULT_CACHE_DIR = WEB_FIXTURES / "verify_cache"
SEED_CACHE_DIR = WEB_FIXTURES / "seed_cache"
"""Read-only snapshots saved from a browser. Kept apart so live runs never overwrite them."""


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


def seed_entry(
    html: str,
    url: str,
    phone: str,
    captured_at: datetime,
    purpose: str,
    phone_purpose: str | None = None,
) -> CachedVerification:
    """Build a seed from a page saved in a browser. Refuses a page that doesn't show `phone`."""
    e164 = checks.normalize_phone(phone)
    if e164 is None or not checks.phone_on_page(e164, html):
        raise ValueError(f"{phone} does not appear on the saved copy of {url}")
    page = FetchedPage(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
        links=extract_links(html, url),
        fetched_at=captured_at,
    )
    return CachedVerification(
        issuer_domain=registered_domain(url),
        purpose=purpose,
        official_phone=e164,
        official_phone_purpose=phone_purpose,
        source_url=url,
        trust_chain=[url],
        fetched_at=captured_at,
        pages=[page],
    )
