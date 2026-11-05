from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
