"""Dump each source PDF's text to a `.txt` beside it, one `=== page N ===` marker per
page, so term pairs can be searched with grep and cited by page.

Dev tool only: it needs PyMuPDF, which is deliberately not in requirements.txt.
Install it in a throwaway venv and run it on the downloaded sources:

    python -m venv /tmp/pdfvenv && /tmp/pdfvenv/bin/pip install pymupdf
    /tmp/pdfvenv/bin/python -I backend/app/glossary/tools/extract_pdf.py \
        backend/app/glossary/_sources/cc/*.pdf

Right-to-left text (Arabic, Persian, Urdu) can come out reversed or with broken
letter joins; check a pair by eye before trusting it.
"""

import sys
from pathlib import Path

import pymupdf


def extract(pdf: Path) -> Path:
    out = pdf.with_suffix(".txt")
    with pymupdf.open(pdf) as doc:
        pages = [
            f"=== page {number} ===\n{page.get_text()}"
            for number, page in enumerate(doc, start=1)
        ]
    out.write_text("\n".join(pages), encoding="utf-8")
    return out


def main(paths: list[str]) -> None:
    for path in paths:
        out = extract(Path(path))
        print(f"{path} -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
