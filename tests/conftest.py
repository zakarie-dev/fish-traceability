import os
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:ci-placeholder@localhost:5432/fish_traceability",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import (
    AuthenticatedHTMLUser,
    get_current_user,
    require_html_user,
)
from app.main import app


@pytest.fixture
def client():
    def override_get_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    """Return a client that bypasses only HTML authentication for page tests."""
    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=uuid4(),
        role="Admin",
    )
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_html_user, None)


def make_user(role="Admin"):
    return SimpleNamespace(
        id=uuid4(),
        email=f"{role.lower()}@example.test",
        hashed_password="not-used",
        role=role,
        assigned_site_id=None,
    )


@pytest.fixture
def authenticate_as():
    def set_user(role="Admin"):
        user = make_user(role)
        app.dependency_overrides[get_current_user] = lambda: user
        return user

    return set_user
