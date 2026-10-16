import os

TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://this_or_that:this_or_that@localhost:5432/this_or_that_test",
)
# Must be set before the app (and its engine) is imported.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def ensure_database(url: str) -> None:
    """Create the database named in `url` if it does not exist."""
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def db_engine():
    from app import models  # noqa: F401  (register tables)
    from app.db import Base, engine

    ensure_database(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(db_engine):
    """Gives a test a schema-ready database and empties every table afterwards."""
    from app.db import Base

    yield db_engine
    with db_engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session(clean_db):
    with Session(clean_db, expire_on_commit=False) as s:
        yield s
