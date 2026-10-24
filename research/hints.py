"""Where the deep pass should look, by document type. Config, not letter-specific logic."""

from typing import Literal

from pydantic import BaseModel


class Hint(BaseModel):
    depth: Literal["deep", "shallow", "unverifiable"]
    anchor_domains: list[str] = []
    search_terms: list[str] = []


def where_to_look(doc_type: str | None) -> Hint:
    """Return the search hint for `doc_type`; unknown types get a generic shallow hint."""
    raise NotImplementedError
