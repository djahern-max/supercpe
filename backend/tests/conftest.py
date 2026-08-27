"""Package tests run against a dedicated `<dbname>_test` database so they can
truncate freely without touching dev data."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.storage import LocalStorage, get_storage


@pytest.fixture(scope="session")
def test_engine():
    dev_url = make_url(settings.database_url)
    test_db = f"{dev_url.database}_test"

    admin_engine = create_engine(dev_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_db},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    admin_engine.dispose()

    engine = create_engine(dev_url.set(database=test_db))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    Session = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.rollback()
    session.close()
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE choices, questions, course_lessons, courses, "
                "lesson_packages, sponsor_profile, sponsor_state_registrations "
                "RESTART IDENTITY"
            )
        )


@pytest.fixture
def storage_root(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    return root


@pytest.fixture
def client(db_session, storage_root):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_storage] = lambda: LocalStorage(storage_root)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    return {"X-Admin-Token": settings.admin_token}
