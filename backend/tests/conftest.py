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
from app.services import auth as auth_service
from app.storage import LocalStorage, get_storage

ADMIN_EMAIL = "admin@supercpe.test"
ADMIN_PASSWORD = "correct-horse-battery"


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
                "TRUNCATE evaluations, evaluation_reviews, audit_exports, "
                "policy_versions, completions, certificate_sequences, "
                "review_answers, lesson_progress, attempt_answers, "
                "attempts, enrollments, choices, questions, "
                "course_reviews, course_lessons, courses, lesson_packages, "
                "site_mode_changes, sponsor_profile, "
                "sponsor_state_registrations, subject_matter_experts, "
                "waiting_list, sessions, accounts RESTART IDENTITY"
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


def make_account(
    db_session,
    email,
    password,
    role,
    must_change_password=False,
):
    return auth_service.create_account(
        db_session,
        email,
        role,
        password,
        created_by=None,
        must_change_password=must_change_password,
    )


def publish_test_policies(db_session, account):
    """Publish the three 8.01 policies: half of the 011/016 launch gate,
    and since 016 a publish requirement too (items 8-10 of the disclosure
    check)."""
    from app.services import policies as policies_service

    for kind in ("registration", "refund", "complaint"):
        policies_service.publish(
            db_session, kind, f"Test {kind} policy.", None, account
        )


def login(client, email, password):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.json()
    return response


@pytest.fixture
def admin_account(db_session):
    return make_account(db_session, ADMIN_EMAIL, ADMIN_PASSWORD, "admin")


@pytest.fixture
def admin_headers(client, admin_account):
    """A logged-in admin client. The session cookie lands in the client's
    cookie jar, so every later request on `client` is the admin — including
    the public GETs prior tests make with no explicit headers, which now
    pass the site-mode gate through the session. The returned dict is empty
    and exists so `headers=admin_headers` call sites keep working."""
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    return {}
