from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException


def test_certificate_missing_consignment_returns_not_found(client, authenticate_as):
    authenticate_as("Admin")
    with patch(
        "app.routes.certificates.generate_certificate_pdf",
        side_effect=HTTPException(status_code=404, detail="Consignment not found"),
    ):
        response = client.get(f"/consignments/{uuid4()}/certificate.pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Consignment not found"
