"""Render the demo's scam letter: a fake "change of address violation" notice sent to
Mariam Namuna, for the scam beat of the demo video.

Modeled on a real scam that targets immigrants: an email posing as ICE about a
missed AR-11 (change of address) that threatens fines, prison, removal and arrest,
demands an immediate call to a non-USCIS number, and says sharing it is a crime
(University of Colorado ISSS scam alert, October 2024). This version adds a
gift-card "compliance fine", which real versions ask for once the person calls.

It is written to trip the research agent's rules (backend/app/research/scam_rules.py):
gift-card payment and arrest threats in the payment section, a non-.gov website,
and a phone number that isn't USCIS's. Everything here is made up; the phone number
is in the 555-01xx fictional range. Same page and font as
i797c_mariam_namuna.py. From the repo root:

    python demo/letters/scam_ar11_mariam_namuna.py

writes scam_ar11_mariam_namuna.png next to this file.
"""

from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

APPLICANT_NAME = "MARIAM NAMUNA"
MAILING_ADDRESS = ("1234 EXAMPLE AVE APT 5", "FREMONT CA 94536")

PAGE_SIZE = (1700, 2200)
"""US Letter at 200 dpi."""
LEFT = 130
RIGHT = PAGE_SIZE[0] - LEFT
TOP = 130
BLOCK_GAP = 24

SMALL, BODY, HEADING, TITLE = 24, 29, 34, 44
"""Font sizes in pixels."""
LINE_HEIGHT = {SMALL: 34, BODY: 39, HEADING: 50, TITLE: 54}


class Line(NamedTuple):
    size: int
    text: str
    right: str = ""
    """Text right-aligned on the same line."""


# An int is extra space, in pixels, before the next line.
LAYOUT: list[Line | int] = [
    Line(SMALL, "U.S. Department of Homeland Security"),
    Line(
        BODY,
        "Immigration and Customs Enforcement",
        right="NOTICE OF VIOLATION",
    ),
    Line(TITLE, "FINAL NOTICE - IMMEDIATE ACTION REQUIRED"),
    30,
    Line(BODY, "Case Number: US16INAR11-0472", right="Notice Date: 10/21/2026"),
    Line(BODY, "Subject: Alien's Change of Address (AR-11)", right="Page 1 of 1"),
    BLOCK_GAP,
    Line(BODY, APPLICANT_NAME),
    *(Line(BODY, address_line) for address_line in MAILING_ADDRESS),
    BLOCK_GAP,
    Line(HEADING, "Notice of Violation"),
    Line(
        BODY,
        "Our records show that you FAILED to file Form AR-11, Alien's Change of "
        "Address, within 10 days of moving.",
    ),
    Line(
        BODY,
        "An investigation has been registered on your immigration documents with "
        "the Department of Justice.",
    ),
    Line(
        BODY,
        "Failure to report a change of address is punishable by a fine, "
        "imprisonment, and removal from the United States.",
    ),
    BLOCK_GAP,
    Line(HEADING, "HOW TO CLOSE YOUR CASE"),
    Line(
        BODY,
        "1. Call the USCIS Verification Unit IMMEDIATELY at (201) 555-0148, within "
        "48 hours of this notice.",
    ),
    Line(
        BODY,
        "2. Pay the $500 compliance fine with Google Play or Apple gift cards. Read "
        "the card numbers to the officer",
    ),
    Line(BODY, "    by phone. Do not send cash or checks."),
    Line(
        BODY,
        "3. Confirm your new address at www.uscis-ar11-verify.com to complete your "
        "background check.",
    ),
    BLOCK_GAP,
    Line(
        BODY,
        "If you do not pay the fine within 48 hours, a warrant will be issued and "
        "you will be arrested by federal",
    ),
    Line(BODY, "officers and placed in deportation proceedings."),
    BLOCK_GAP,
    Line(
        BODY,
        "This notice is confidential. Sharing it with a lawyer or any third party "
        "is a federal offense.",
    ),
    BLOCK_GAP,
    Line(BODY, "Officer R. Daniels"),
    Line(BODY, "USCIS Verification Unit, Enforcement Division"),
    Line(BODY, "Phone: (201) 555-0148"),
    BLOCK_GAP,
    Line(SMALL, "Form AR-11-V 09/26"),
]


def render() -> Image.Image:
    page = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(page)
    y = TOP
    for item in LAYOUT:
        if isinstance(item, int):
            y += item
            continue
        font = ImageFont.load_default(size=item.size)
        draw.text((LEFT, y), item.text, font=font, fill="black")
        if item.right:
            draw.text((RIGHT, y), item.right, font=font, fill="black", anchor="ra")
        y += LINE_HEIGHT[item.size]
    return page


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".png")
    render().save(out)
    print(f"wrote {out}")
