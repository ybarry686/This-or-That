from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DATABASE_URL, ensure_database

MIGRATIONS_DB_URL = make_url(TEST_DATABASE_URL).set(database="this_or_that_migrations_test")


def test_migrations_match_models_and_downgrade_cleanly(monkeypatch):
    from app import models  # noqa: F401
    from app.config import get_settings
    from app.db import Base

    url = MIGRATIONS_DB_URL.render_as_string(hide_password=False)
    ensure_database(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []

        command.downgrade(config, "base")
    finally:
        get_settings.cache_clear()
        engine.dispose()
