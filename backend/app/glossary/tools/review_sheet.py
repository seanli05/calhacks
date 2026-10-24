"""Write a checker's review sheet for one language from `terms.csv`.

    python backend/app/glossary/tools/review_sheet.py fa   # -> review_fa.csv
    python backend/app/glossary/tools/review_sheet.py ne   # -> review_ne.csv

Machine rows come first, since they need a human most. The checker fills in
`checker_ok` (yes/no) and `checker_fix`; copy accepted fixes back into `terms.csv` by
hand. Never turn a row into `community` without that check.
"""

import csv
import re
import sys
from pathlib import Path

GLOSSARY_DIR = Path(__file__).resolve().parent.parent
_FARSI = re.compile(r"farsi(?: \([^)]*\))?: ([^.;]+?)(?: \(NYC[^)]*\))?(?:[.;]|$)")


def farsi_variant(row: dict[str, str]) -> str:
    """The Iranian Farsi form from the note, or the Dari form when the note says
    they're the same."""
    match = _FARSI.search(row["note"])
    if match:
        return match.group(1).strip()
    return row["translation"] if "Same in Farsi" in row["note"] else ""


def review_rows(language: str) -> list[dict[str, str]]:
    with (GLOSSARY_DIR / "terms.csv").open(encoding="utf-8", newline="") as f:
        rows = [row for row in csv.DictReader(f) if row["language"] == language]
    rows.sort(key=lambda row: row["trust_level"] != "machine")
    text_column = {"fa": "dari", "ne": "nepali"}.get(language, "translation")
    sheet = []
    for row in rows:
        entry = {"term": row["term"], text_column: row["translation"]}
        if language == "fa":
            entry["farsi_variant"] = farsi_variant(row)
        entry |= {
            "trust_level": row["trust_level"],
            "note": row["note"],
            "checker_ok": "",
            "checker_fix": "",
        }
        sheet.append(entry)
    return sheet


def main(language: str) -> None:
    sheet = review_rows(language)
    out = GLOSSARY_DIR / f"review_{language}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(sheet[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sheet)
    print(f"{out}: {len(sheet)} rows")


if __name__ == "__main__":
    main(sys.argv[1])
