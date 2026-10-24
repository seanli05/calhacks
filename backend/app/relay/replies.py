"""Parse numbered WhatsApp replies ("1", "2.", " 2 "). Options are 1-based (C5)."""

import re

_CHOICE = re.compile(r"^(\d{1,2})[.)]?$")


def parse_choice(text: str, n_options: int) -> int | None:
    """A numbered reply within 1..n_options, else None."""
    match = _CHOICE.match(text.strip())
    if match is None:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= n_options else None
