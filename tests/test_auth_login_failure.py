from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError


def test_login_rejects_bad_credentials(client):
    with patch(
        "app.routes.auth.AuthService.authenticate",
        side_effect=HTTPException(status_code=401, detail="Incorrect email or password"),
    ):
        response = client.post(
            "/auth/login",
            json={"email": "admin@example.test", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_html_login_redirects_with_service_message_when_database_is_unavailable(
    client,
):
    with patch(
        "app.routes.auth.AuthService.authenticate",
        side_effect=OperationalError("SELECT users", {}, OSError("database unavailable")),
    ):
        response = client.post(
            "/auth/login",
            data={"email": "admin@example.test", "password": "valid-password"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=unavailable"
    login_page = client.get(response.headers["location"])
    assert "Check the DATABASE_URL host in" in login_page.text


def test_json_login_returns_service_unavailable_when_database_is_unavailable(client):
    with patch(
        "app.routes.auth.AuthService.authenticate",
        side_effect=OperationalError("SELECT users", {}, OSError("database unavailable")),
    ):
        response = client.post(
            "/auth/login",
            json={"email": "admin@example.test", "password": "valid-password"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service is temporarily unavailable"
