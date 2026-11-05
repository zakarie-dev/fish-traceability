from unittest.mock import patch
from uuid import uuid4


def test_admin_can_download_certificate(client, authenticate_as):
    authenticate_as("Admin")
    with patch(
        "app.routes.certificates.generate_certificate_pdf", return_value=b"%PDF-test"
    ):
        response = client.get(f"/consignments/{uuid4()}/certificate.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-test"
