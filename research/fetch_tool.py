"""Client-side `fetch_page` tool for the deep pass.

Every official number is checked against HTML this module fetched, so it is the
trust foundation: it refuses private addresses, directory sites, and URLs that
carry identifiers, and it re-checks every redirect hop. Record/replay keeps
tests and the demo fallback offline.
"""

import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import tldextract
from bs4 import BeautifulSoup
from pydantic import BaseModel

from research.hints import BLOCKED_DOMAINS, ID_SHAPED_PATTERNS

TIMEOUT_S = 10.0
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
MODEL_TEXT_CHARS = 15_000
MODEL_MAX_LINKS = 60
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
RECORDED_AT_HEADER = "x-recorded-at"
WEB_FIXTURES = Path("fixtures/web")

# Bundled public suffix list only; never download it at run time.
_extract = tldextract.TLDExtract(suffix_list_urls=())

Resolver = Callable[[str], Awaitable[list[str]]]


class FetchRefused(Exception):
    """The URL is not allowed: non-http(s), private/localhost IP, or a blocked directory domain."""


class FetchedPage(BaseModel):
    url: str
    final_url: str
    status_code: int
    html: str
    links: list[str]
    fetched_at: datetime


def registered_domain(url_or_host: str) -> str:
    """`www.uscis.gov` or a URL -> `uscis.gov`. Empty string if there is none."""
    host = urlsplit(url_or_host).hostname if "//" in url_or_host else url_or_host
    ext = _extract((host or "").lower())
    return ext.top_domain_under_public_suffix or ext.domain


def is_gov(url_or_host: str) -> bool:
    """True for a .gov registered domain (registration is restricted to US government bodies)."""
    return registered_domain(url_or_host).endswith(".gov")


async def system_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, None, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return addr.is_global and not addr.is_multicast


async def check_url(url: str, resolve: Resolver = system_resolver) -> None:
    """Raise FetchRefused unless `url` may be fetched."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchRefused(f"only http(s) URLs are allowed, got {parts.scheme!r}")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise FetchRefused("URL has no host")
    if host == "localhost" or host.endswith(".localhost"):
        raise FetchRefused("localhost is not allowed")
    domain = registered_domain(host)
    if domain in BLOCKED_DOMAINS:
        raise FetchRefused(f"{domain} is a phone-directory site; use the official site")
    if any(p.search(url) for p in ID_SHAPED_PATTERNS):
        raise FetchRefused("URL contains an identifier-shaped value")
    try:
        ips = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            ips = await resolve(host)
        except OSError as exc:
            raise FetchRefused(f"could not resolve {host}: {exc}") from exc
    if not ips or not all(_ip_is_public(ip) for ip in ips):
        raise FetchRefused(f"{host} resolves to a private or reserved address")


def extract_links(html: str, base_url: str) -> list[str]:
    """Absolute targets of every real `<a href>`, including tel: links, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, href).split("#")[0]
        if absolute not in links:
            links.append(absolute)
    return links


async def fetch_page(
    url: str, *, http: httpx.AsyncClient, resolve: Resolver = system_resolver
) -> FetchedPage:
    """Fetch one page, keeping the raw HTML and the real `<a href>` links.

    http(s) only, no private IPs, size cap, 10 s timeout, browser-like UA.
    Raises FetchRefused for disallowed URLs and httpx errors for network failures.
    """
    async with asyncio.timeout(TIMEOUT_S):
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(current, resolve)
            async with http.stream(
                "GET",
                current,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"},
                follow_redirects=False,
                timeout=TIMEOUT_S,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise httpx.HTTPError(
                            f"redirect without location from {current}"
                        )
                    current = urljoin(current, location)
                    continue
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith(ALLOWED_CONTENT_TYPES):
                    raise FetchRefused(
                        f"content type {content_type!r} is not HTML or text"
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_BYTES:
                        del body[MAX_BYTES:]
                        break
                html = body.decode(response.encoding or "utf-8", errors="replace")
                recorded = response.headers.get(RECORDED_AT_HEADER)
                return FetchedPage(
                    url=url,
                    final_url=current,
                    status_code=response.status_code,
                    html=html,
                    links=extract_links(html, current),
                    fetched_at=datetime.fromisoformat(recorded)
                    if recorded
                    else datetime.now(UTC),
                )
        raise FetchRefused(f"more than {MAX_REDIRECTS} redirects")


def page_text_for_model(page: FetchedPage, related_domains: list[str] = ()) -> str:
    """The only view of a page the model gets: visible text plus same-site links.

    Scripts and styles are stripped and text is truncated to ~15k characters.
    Up to 60 links on the page's own registered domain or a related one are listed.
    """
    soup = BeautifulSoup(page.html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    text = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n"))
    text = re.sub(r"[ \t\xa0]+", " ", text).strip()[:MODEL_TEXT_CHARS]

    domains = {registered_domain(page.final_url), *related_domains}
    lines: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        target = urljoin(page.final_url, a["href"].strip()).split("#")[0]
        if target in seen:
            continue
        is_tel = target.startswith("tel:")
        if not is_tel and (
            not target.startswith("http") or registered_domain(target) not in domains
        ):
            continue
        seen.add(target)
        label = " ".join(a.get_text(" ").split())[:80]
        lines.append(f"- {label} -> {target}")
        if len(lines) >= MODEL_MAX_LINKS:
            break
    return (
        f"URL: {page.final_url}\nHTTP status: {page.status_code}\n\n{text}\n\n"
        "Links on this page:\n" + "\n".join(lines)
    )


# --- Record / replay ---


def _fixture_path(directory: Path, url: str) -> Path:
    return directory / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes requests through and saves each response (every redirect hop) to `directory`."""

    def __init__(self, directory: Path = WEB_FIXTURES) -> None:
        self._directory = directory
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        body = bytearray()
        async for chunk in response.aiter_raw():
            body.extend(chunk)
            if len(body) >= MAX_BYTES:
                break
        await response.aclose()
        recorded_at = datetime.now(UTC).isoformat()
        headers = {
            k: response.headers[k]
            for k in ("content-type", "location", "content-encoding")
            if k in response.headers
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        _fixture_path(self._directory, str(request.url)).write_text(
            json.dumps(
                {
                    "url": str(request.url),
                    "fetched_at": recorded_at,
                    "status_code": response.status_code,
                    "headers": headers,
                    "body": bytes(body).decode("latin-1"),
                },
                indent=1,
            )
        )
        return httpx.Response(
            response.status_code,
            headers={**headers, RECORDED_AT_HEADER: recorded_at},
            content=bytes(body),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def save_fixture(
    directory: Path,
    url: str,
    body: str,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    fetched_at: datetime | None = None,
) -> None:
    """Write one replayable response, in the same format RecordingTransport uses."""
    directory.mkdir(parents=True, exist_ok=True)
    _fixture_path(directory, url).write_text(
        json.dumps(
            {
                "url": url,
                "fetched_at": (fetched_at or datetime.now(UTC)).isoformat(),
                "status_code": status_code,
                "headers": headers or {"content-type": "text/html; charset=utf-8"},
                "body": body.encode().decode("latin-1"),
            },
            indent=1,
        )
    )


def replay_transport(directory: Path = WEB_FIXTURES) -> httpx.MockTransport:
    """Serve only recorded responses. An unrecorded URL is a connection error."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = _fixture_path(directory, str(request.url))
        if not path.exists():
            raise httpx.ConnectError(f"not recorded: {request.url}", request=request)
        saved = json.loads(path.read_text())
        return httpx.Response(
            saved["status_code"],
            headers={**saved["headers"], RECORDED_AT_HEADER: saved["fetched_at"]},
            content=saved["body"].encode("latin-1"),
        )

    return httpx.MockTransport(handler)


async def replay_resolver(host: str) -> list[str]:
    """Replay never touches the network, so names resolve to a public placeholder.

    Literal IPs and localhost are still refused by check_url before this runs.
    """
    return ["93.184.215.14"]
