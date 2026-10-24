"""Turn one uploaded page (photo or PDF) into Claude content blocks."""

import asyncio
import base64
import io

from anthropic.types import DocumentBlockParam, ImageBlockParam
from PIL import Image, ImageOps, UnidentifiedImageError

ContentBlock = ImageBlockParam | DocumentBlockParam

MAX_LONG_SIDE_PX = 2000
JPEG_QUALITY = 85
# Base64 grows a file by 4/3, and the whole request must stay under 32 MB.
MAX_PDF_BYTES = 20 * 1024 * 1024

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
PDF_TYPE = "application/pdf"

TIP_UNSUPPORTED = "Please send it as a regular photo (JPEG) or PDF."
TIP_UNREADABLE = "I couldn't open that file. Please take a new photo of the letter and send it again."
TIP_PDF_TOO_BIG = (
    "That PDF is too large. Please send photos of the pages instead, or a smaller PDF."
)


class UnsupportedMedia(ValueError):
    """The upload can't be read (e.g. HEIC). The message is a user-facing tip in English."""


async def to_content_blocks(data: bytes, content_type: str) -> list[ContentBlock]:
    """Return content blocks for one page image or PDF.

    Accepts JPEG, PNG, WebP and PDF. Images are EXIF-rotated and scaled to at
    most 2000 px on the long side; Pillow work runs off the event loop.
    Raises UnsupportedMedia for anything else.
    """
    media_type = content_type.split(";")[0].strip().lower()
    if media_type == PDF_TYPE:
        return [_pdf_block(data)]
    if media_type in IMAGE_TYPES:
        jpeg = await asyncio.to_thread(_normalize_image, data)
        return [
            ImageBlockParam(
                type="image",
                source={
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode("ascii"),
                },
            )
        ]
    raise UnsupportedMedia(TIP_UNSUPPORTED)


def _pdf_block(data: bytes) -> DocumentBlockParam:
    if not data.startswith(b"%PDF"):
        raise UnsupportedMedia(TIP_UNREADABLE)
    if len(data) > MAX_PDF_BYTES:
        raise UnsupportedMedia(TIP_PDF_TOO_BIG)
    return DocumentBlockParam(
        type="document",
        source={
            "type": "base64",
            "media_type": PDF_TYPE,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    )


def _normalize_image(data: bytes) -> bytes:
    """EXIF-rotate, flatten to RGB, cap the long side, and re-encode as JPEG."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, "white")
                background.paste(img, mask=img.getchannel("A"))
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((MAX_LONG_SIDE_PX, MAX_LONG_SIDE_PX))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise UnsupportedMedia(TIP_UNREADABLE) from e
