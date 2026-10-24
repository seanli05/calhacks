"""Dump a saved HTML page's visible text to a `.txt` beside it, plus the page's
language-switcher links (`hreflang`), so English and translated pages can be
compared side by side. Standard library only.

    python -I backend/app/glossary/tools/html_text.py backend/app/glossary/_sources/uscis_es/*.html

Fetch the pages yourself first (e.g. with curl) into `_sources/`, which git ignores.
"""

import sys
from html.parser import HTMLParser
from pathlib import Path

_SKIP = {"script", "style", "noscript", "svg"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "tr", "div", "br", "td", "th"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skipping += 1
        if tag in _BLOCK:
            self.parts.append("\n")
        values = dict(attrs)
        if values.get("hreflang") and values.get("href"):
            self.links.append(f"{values['hreflang']} {values['href']}")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skipping:
            self._skipping -= 1
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def extract(page: Path) -> Path:
    parser = _Text()
    parser.feed(page.read_text(encoding="utf-8", errors="replace"))
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    text = "\n".join(line for line in lines if line)
    links = "\n".join(sorted(set(parser.links)))
    out = page.with_suffix(".txt")
    out.write_text(f"=== hreflang links ===\n{links}\n=== text ===\n{text}\n", "utf-8")
    return out


def main(paths: list[str]) -> None:
    for path in paths:
        out = extract(Path(path))
        print(f"{path} -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
