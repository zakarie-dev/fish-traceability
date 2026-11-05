def test_login_rejects_invalid_request_body(client):
    response = client.post("/auth/login", json={"email": "x", "password": ""})

    assert response.status_code == 422


def test_vessel_rejects_missing_required_fields(client, authenticate_as):
    authenticate_as("Admin")

    response = client.post("/vessels", json={"name": "Incomplete"})

    assert response.status_code == 422
