import asyncio
import base64
import io

import pytest
from PIL import Image

from research.preprocess import (
    MAX_LONG_SIDE_PX,
    MAX_PDF_BYTES,
    UnsupportedMedia,
    to_content_blocks,
)

EXIF_ORIENTATION = 0x0112


def jpeg_bytes(size: tuple[int, int], orientation: int | None = None) -> bytes:
    img = Image.new("RGB", size, "white")
    out = io.BytesIO()
    if orientation is None:
        img.save(out, format="JPEG")
    else:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION] = orientation
        img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def decode(block: dict) -> Image.Image:
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/jpeg"
    return Image.open(io.BytesIO(base64.standard_b64decode(block["source"]["data"])))


def convert(data: bytes, content_type: str) -> list:
    return asyncio.run(to_content_blocks(data, content_type))


def test_exif_rotation_applied() -> None:
    # Orientation 6 = rotate 90° clockwise to display: a landscape file shows as portrait.
    [block] = convert(jpeg_bytes((400, 200), orientation=6), "image/jpeg")
    assert decode(block).size == (200, 400)


def test_resize_cap() -> None:
    [block] = convert(jpeg_bytes((4000, 3000)), "image/jpeg")
    assert max(decode(block).size) == MAX_LONG_SIDE_PX


def test_small_image_not_upscaled() -> None:
    [block] = convert(jpeg_bytes((800, 600)), "image/jpeg")
    assert decode(block).size == (800, 600)


def test_png_with_alpha_becomes_jpeg() -> None:
    out = io.BytesIO()
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(out, format="PNG")
    [block] = convert(out.getvalue(), "image/png")
    assert decode(block).getpixel((50, 50)) == (255, 255, 255)


@pytest.mark.parametrize("content_type", ["image/heic", "image/heif", "text/plain"])
def test_heic_and_others_rejected_with_tip(content_type: str) -> None:
    with pytest.raises(UnsupportedMedia, match="JPEG"):
        convert(b"whatever", content_type)


def test_pdf_passthrough() -> None:
    pdf = b"%PDF-1.4\n%fake pdf body\n"
    [block] = convert(pdf, "application/pdf")
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(block["source"]["data"]) == pdf


def test_pdf_too_big_rejected() -> None:
    with pytest.raises(UnsupportedMedia):
        convert(b"%PDF" + b"0" * MAX_PDF_BYTES, "application/pdf")


def test_corrupt_image_rejected() -> None:
    with pytest.raises(UnsupportedMedia, match="photo"):
        convert(b"\xff\xd8\xff not really a jpeg", "image/jpeg")
