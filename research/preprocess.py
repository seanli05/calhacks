"""Turn one uploaded page (photo or PDF) into Claude content blocks."""

from anthropic.types import DocumentBlockParam, ImageBlockParam

ContentBlock = ImageBlockParam | DocumentBlockParam


class UnsupportedMedia(ValueError):
    """The upload can't be read (e.g. HEIC). The message is a user-facing tip in English."""


async def to_content_blocks(data: bytes, content_type: str) -> list[ContentBlock]:
    """Return content blocks for one page image or PDF.

    Accepts JPEG, PNG, WebP and PDF. Images are EXIF-rotated and scaled to at
    most 2000 px on the long side; Pillow work runs off the event loop.
    Raises UnsupportedMedia for anything else.
    """
    raise NotImplementedError
