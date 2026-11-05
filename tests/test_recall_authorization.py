def test_recall_requires_admin_role(client, authenticate_as):
    authenticate_as("Inspector")

    response = client.post("/recall/20000000-0000-4000-8000-000000000001")

    assert response.status_code == 403
