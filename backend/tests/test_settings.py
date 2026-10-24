from app.settings import Settings, to_asyncpg_url


def test_neon_url_is_rewritten_for_asyncpg() -> None:
    url = "postgresql://u:p@ep-x.us-west-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
    assert (
        to_asyncpg_url(url)
        == "postgresql+asyncpg://u:p@ep-x.us-west-2.aws.neon.tech/neondb?ssl=require"
    )


def test_asyncpg_url_passes_through() -> None:
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/calhacks"
    assert to_asyncpg_url(url) == url


def test_unpooled_url_is_preferred() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://u:p@ep-x-pooler.neon.tech/db?sslmode=require",
        database_url_unpooled="postgresql://u:p@ep-x.neon.tech/db?sslmode=require",
    )
    assert (
        settings.async_database_url
        == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"
    )
