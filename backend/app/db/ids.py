"""Prefixed IDs (Plan.md C19): `<prefix>_<16 hex chars>`."""

import secrets


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"
