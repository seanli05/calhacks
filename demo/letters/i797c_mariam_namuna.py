"""Render Mariam Namuna's demo letter, a mock Form I-797C asylum interview notice.

The layout copies the research fixture
backend/tests/fixtures/research/letters/i797c_asylum_interview/page_1.png line
for line: same page, font, positions, line breaks and text. Only the applicant
name and the mailing address differ. The case values match SF_DEMO_CASE in
mock_agency/agency/case_record.py, the case the mock line knows with
MOCK_AGENCY_CASE=sf_demo. Everything here is made up.

Uses only Pillow and its bundled default font (Aileron Regular). From the repo
root:

    python demo/letters/i797c_mariam_namuna.py

writes i797c_mariam_namuna.png next to this file.
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
    Line(SMALL, "Department of Homeland Security"),
    Line(
        BODY,
        "U.S. Citizenship and Immigration Services",
        right="Form I-797C, Notice of Action",
    ),
    Line(TITLE, "THE UNITED STATES OF AMERICA"),
    30,
    Line(BODY, "Receipt Number: ZLA2690412873", right="Case Type: I-589"),
    Line(SMALL, "APPLICATION FOR ASYLUM AND FOR WITHHOLDING OF REMOVAL"),
    Line(BODY, "Received Date: 03/27/2026", right="Notice Date: 10/19/2026"),
    Line(BODY, "Applicant: A-219-555-031", right="Page 1 of 1"),
    Line(BODY, APPLICANT_NAME),
    BLOCK_GAP,
    Line(SMALL, "USCIS San Francisco Asylum Office"),
    Line(SMALL, "P.O. Box 77530, San Francisco, CA 94107"),
    BLOCK_GAP,
    Line(BODY, APPLICANT_NAME),
    *(Line(BODY, address_line) for address_line in MAILING_ADDRESS),
    BLOCK_GAP,
    Line(HEADING, "Notice Type: Asylum Interview Appointment"),
    Line(
        BODY,
        "You are scheduled for an interview on your Form I-589 at the date, time "
        "and place shown below. Please arrive",
    ),
    Line(BODY, "30 minutes early."),
    Line(BODY, "Interview Date: November 25, 2026 Time: 08:30 AM"),
    Line(
        BODY,
        "Location: USCIS San Francisco Asylum Office, 75 Hawthorne Street, "
        "Suite 303S, San Francisco, CA 94105",
    ),
    BLOCK_GAP,
    Line(HEADING, "I. WHO SHOULD COME TO THE INTERVIEW"),
    Line(
        BODY,
        "You must bring every dependent listed on your Form I-589 to the interview.",
    ),
    Line(
        BODY,
        "If you are not fluent in English, you must bring an interpreter. Your "
        "interpreter must be at least 18 years old and",
    ),
    Line(
        BODY,
        "fluent in English and your language. Your interpreter may not be your "
        "attorney or representative of record, a",
    ),
    Line(
        BODY,
        "witness testifying for you, an employee of the government of your country "
        "of nationality, or a person with a",
    ),
    Line(BODY, "pending asylum application who has not yet been interviewed."),
    Line(
        BODY,
        "If your attorney or accredited representative will take part by phone, "
        "they must send the remote participation",
    ),
    Line(BODY, "election at least 10 days before the interview."),
    BLOCK_GAP,
    Line(HEADING, "II. WHAT TO BRING"),
    Line(BODY, "- Any passport and identity document for you and each dependent."),
    Line(
        BODY,
        "- The original and one copy of documents showing your relationship to "
        "each dependent, such as marriage and",
    ),
    Line(BODY, "birth certificates."),
    Line(BODY, "- Form I-94, Arrival/Departure Record, if you have one."),
    Line(BODY, "- Two copies of any additional evidence you want USCIS to consider."),
    BLOCK_GAP,
    Line(
        BODY,
        "If you cannot come, send a written request to reschedule to the office "
        "above before your interview date. If you",
    ),
    Line(
        BODY,
        "do not appear, your application may be referred to an immigration judge "
        "or dismissed.",
    ),
    Line(
        BODY,
        "For more information visit www.uscis.gov or www.uscis.gov/contactcenter.",
    ),
    BLOCK_GAP,
    Line(SMALL, "Form I-797C 04/01/24"),
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
