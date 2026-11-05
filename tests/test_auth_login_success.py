from unittest.mock import patch

from app.schemas import TokenResponse


def test_login_returns_access_token(client):
    with patch(
        "app.routes.auth.AuthService.authenticate",
        return_value=TokenResponse(access_token="signed-token"),
    ) as authenticate:
        response = client.post(
            "/auth/login",
            json={"email": "admin@example.test", "password": "valid-password"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "signed-token",
        "token_type": "bearer",
    }
    authenticate.assert_called_once()
