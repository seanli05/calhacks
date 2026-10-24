"""Client-side `fetch_page` tool for the deep pass."""

from datetime import datetime

import httpx
from pydantic import BaseModel


class FetchRefused(Exception):
    """The URL is not allowed: non-http(s), private/localhost IP, or a blocked directory domain."""


class FetchedPage(BaseModel):
    url: str
    final_url: str
    status_code: int
    html: str
    links: list[str]
    fetched_at: datetime


async def fetch_page(url: str, *, http: httpx.AsyncClient) -> FetchedPage:
    """Fetch one page, keeping the raw HTML and the real `<a href>` links.

    http(s) only, no private IPs, size cap, 10 s timeout, browser-like UA.
    Raises FetchRefused for disallowed URLs and httpx errors for network failures.
    """
    raise NotImplementedError
