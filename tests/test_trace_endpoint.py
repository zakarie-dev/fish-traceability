from unittest.mock import patch
from uuid import uuid4

from app.schemas import LotTraceResponse


def test_trace_endpoint_returns_lineage(client):
    lot_id = uuid4()
    payload = LotTraceResponse(
        lot_id=lot_id,
        lot_code="LOT-TRACE-1",
        backward_lots=[],
        forward_consignments=[],
    )
    with patch(
        "app.routes.traceability.TraceabilityService.get_trace", return_value=payload
    ):
        response = client.get("/trace/LOT-TRACE-1")

    assert response.status_code == 200
    assert response.json()["lot_id"] == str(lot_id)
    assert response.json()["lot_code"] == "LOT-TRACE-1"
