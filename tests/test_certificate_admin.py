from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import qrcode

from app.database import get_db
from app.dependencies import require_html_user
from app.main import app


def test_admin_can_download_certificate(client, monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="Admin")
    db = MagicMock()
    monkeypatch.setitem(app.dependency_overrides, require_html_user, lambda: user)
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
    with patch(
        "app.routes.certificates.generate_certificate_pdf", return_value=b"%PDF-test"
    ) as generate_pdf:
        response = client.get(f"/consignments/{uuid4()}/certificate.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-test"
    audit = db.add.call_args.args[0]
    assert audit.action == "certificate.issue"
    assert audit.user_id == user.id
    db.commit.assert_called_once_with()
    generate_pdf.assert_called_once()


def test_certificate_qr_uses_public_base_url(monkeypatch):
    from app.services.certificate_service import generate_certificate_pdf

    consignment_id = uuid4()
    lot_id = uuid4()
    consignment = SimpleNamespace(
        buyer_name="Gulf Seafood LLC",
        destination_country="UAE",
        shipping_date=date(2026, 11, 12),
        container_number="DEMO-QR-1",
    )
    lot = SimpleNamespace(
        id=lot_id,
        lot_code="LOT/QR 1",
        current_weight=Decimal("10.00"),
        catch_id=None,
    )
    repository = MagicMock()
    repository.get_ancestor_ids.return_value = [lot_id]
    repository.get_lots.side_effect = [[lot], [lot]]
    repository.get_catches.return_value = []
    repository.get_vessels.return_value = []
    db = MagicMock()
    db.scalar.return_value = consignment
    db.scalars.return_value = [lot_id]
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://fish.example.org/")

    with (
        patch(
            "app.services.certificate_service.LotRepository",
            return_value=repository,
        ),
        patch(
            "app.services.certificate_service.qrcode.make",
            wraps=qrcode.make,
        ) as make_qr,
    ):
        pdf = generate_certificate_pdf(db, consignment_id)

    assert pdf.startswith(b"%PDF")
    make_qr.assert_called_once_with(
        "https://fish.example.org/trace/LOT%2FQR%201"
    )
