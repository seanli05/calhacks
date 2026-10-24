import pytest

from research.fakes import FakeResearchDB


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeResearchDB:
    """The DB helpers research calls, swapped for an in-memory fake."""
    return FakeResearchDB().install(monkeypatch)
