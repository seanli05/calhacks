from collections.abc import Mapping

from fastapi import Request
from twilio.request_validator import RequestValidator

from app.settings import Settings


def is_valid_twilio_request(
    request: Request, params: Mapping[str, str], settings: Settings
) -> bool:
    """Check the X-Twilio-Signature header against the request.

    Twilio signs the public URL it called, but ngrok rewrites the host, so the URL is
    rebuilt from PUBLIC_BASE_URL rather than taken from the request.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, dict(params), signature)
