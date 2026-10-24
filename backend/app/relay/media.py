"""Download WhatsApp media from Twilio."""

import httpx
from pydantic import BaseModel

from app.settings import Settings

MEDIA_DOWNLOAD_TIMEOUT_S = 10.0


class MediaDownloadError(Exception):
    """Twilio media couldn't be fetched."""


class DownloadedMedia(BaseModel):
    content_type: str
    data: bytes


async def download_media(
    client: httpx.AsyncClient,
    url: str,
    content_type: str,
    message_sid: str,
    settings: Settings,
) -> DownloadedMedia:
    """Fetch a MediaUrl with Twilio credentials.

    Twilio redirects to a signed CDN URL; httpx drops the auth header on cross-origin
    redirects, so credentials only go to Twilio.
    """
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    try:
        response = await client.get(
            url, auth=auth, follow_redirects=True, timeout=MEDIA_DOWNLOAD_TIMEOUT_S
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # Don't put the exception text in the message: it can include the media URL.
        raise MediaDownloadError(
            f"Media download failed for {message_sid}: {type(exc).__name__}"
        ) from exc
    return DownloadedMedia(content_type=content_type, data=response.content)
