"""fetch_page refusals, redirects, link extraction, and record/replay. No network."""

import httpx
import pytest
from app.research.fetch_tool import (
    FetchedPage,
    FetchRefused,
    check_url,
    extract_links,
    fetch_page,
    page_text_for_model,
    replay_resolver,
    replay_transport,
    save_fixture,
)


async def public_resolver(host: str) -> list[str]:
    return ["93.184.215.14"]


async def private_resolver(host: str) -> list[str]:
    return ["10.1.2.3"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.gov/file",
        "http://localhost:8000/",
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "https://www.gethuman.com/phone/uscis",
        "https://sub.800notes.com/x",
        "https://www.uscis.gov/case-status?receipt=IOE1234567890",
        "https://example.gov/lookup/A123456789",
        "https://example.gov/q?ssn=123-45-6789",
    ],
)
@pytest.mark.asyncio
async def test_check_url_refuses(url: str) -> None:
    with pytest.raises(FetchRefused):
        await check_url(url, public_resolver)


@pytest.mark.asyncio
async def test_hostname_resolving_to_private_ip_is_refused() -> None:
    with pytest.raises(FetchRefused):
        await check_url("https://intranet.example.com/", private_resolver)


@pytest.mark.asyncio
async def test_public_url_allowed() -> None:
    await check_url("https://www.uscis.gov/contactcenter", public_resolver)


@pytest.mark.asyncio
async def test_redirect_to_private_ip_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://192.168.1.1/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FetchRefused):
            await fetch_page(
                "https://www.example.gov/", http=http, resolve=public_resolver
            )


@pytest.mark.asyncio
async def test_redirect_followed_and_rechecked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<a href="/contact">Contact</a>',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        page = await fetch_page(
            "https://www.example.gov/old", http=http, resolve=public_resolver
        )
    assert page.final_url == "https://www.example.gov/new"
    assert page.links == ["https://www.example.gov/contact"]


@pytest.mark.asyncio
async def test_too_many_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FetchRefused):
            await fetch_page(
                "https://www.example.gov/", http=http, resolve=public_resolver
            )


@pytest.mark.asyncio
async def test_non_html_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FetchRefused):
            await fetch_page(
                "https://www.example.gov/a.pdf", http=http, resolve=public_resolver
            )


def test_extract_links_absolute_with_tel() -> None:
    html = """
      <a href="/contactcenter">Contact</a>
      <a href="https://other.org/page#frag">Other</a>
      <a href="tel:+18005550100">Call</a>
      <a href="#top">Top</a><a href="mailto:x@y.gov">Mail</a>
      <a href="/contactcenter">Duplicate</a>
    """
    assert extract_links(html, "https://www.example.gov/about/") == [
        "https://www.example.gov/contactcenter",
        "https://other.org/page",
        "tel:+18005550100",
    ]


def test_page_text_strips_scripts_and_filters_links() -> None:
    page = FetchedPage(
        url="https://www.example.gov/",
        final_url="https://www.example.gov/",
        status_code=200,
        html="""<html><script>ignore()</script><style>.x{}</style>
          <p>Hello visitor</p>
          <a href="/inside">Inside</a><a href="https://elsewhere.com/">Out</a>
          <a href="https://partner.gov/x">Partner</a></html>""",
        links=[],
        fetched_at="2026-10-23T00:00:00Z",
    )
    text = page_text_for_model(page, ["partner.gov"])
    assert "Hello visitor" in text
    assert "ignore()" not in text
    assert "https://www.example.gov/inside" in text
    assert "https://partner.gov/x" in text
    assert "elsewhere.com" not in text


@pytest.mark.asyncio
async def test_replay_serves_only_recorded(tmp_path) -> None:
    save_fixture(tmp_path, "https://www.example.gov/", "<p>recorded</p>")
    async with httpx.AsyncClient(transport=replay_transport(tmp_path)) as http:
        page = await fetch_page(
            "https://www.example.gov/", http=http, resolve=replay_resolver
        )
        assert "recorded" in page.html
        with pytest.raises(httpx.ConnectError):
            await fetch_page(
                "https://www.example.gov/missing", http=http, resolve=replay_resolver
            )
