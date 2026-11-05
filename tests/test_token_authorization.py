def test_recall_rejects_invalid_bearer_token(client):
    response = client.post(
        "/recall/20000000-0000-4000-8000-000000000001",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
