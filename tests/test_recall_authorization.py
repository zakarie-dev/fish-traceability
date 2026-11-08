from unittest.mock import patch

from app.schemas import RecallResponse


def test_recall_requires_admin_or_inspector_role(client, authenticate_as):
    authenticate_as("Officer")

    response = client.post("/recall/20000000-0000-4000-8000-000000000001")

    assert response.status_code == 403


def test_inspector_can_recall_lot(client, authenticate_as):
    authenticate_as("Inspector")
    with patch(
        "app.routes.traceability.TraceabilityService.recall_lot",
        return_value=RecallResponse(affected_lot_ids=[], affected_buyers=[]),
    ):
        response = client.post("/recall/20000000-0000-4000-8000-000000000001")

    assert response.status_code == 200
    assert response.json() == {"affected_lot_ids": [], "affected_buyers": []}
