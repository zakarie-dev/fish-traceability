from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.lot_service import LotService


def test_split_rejects_nonconserving_weights(monkeypatch):
    parent = SimpleNamespace(
        id=uuid4(),
        current_weight=Decimal("100.00"),
        catch_id=uuid4(),
        species_id=uuid4(),
        status="Available",
    )

    class FakeLotRepository:
        def __init__(self, _db):
            pass

        def get_lot(self, _lot_id, for_update=False):
            return parent

    session = SimpleNamespace(begin=lambda: nullcontext())
    monkeypatch.setattr("app.services.lot_service.LotRepository", FakeLotRepository)

    with pytest.raises(HTTPException) as error:
        LotService(session).split_lot(parent.id, [40, 50], 5)

    assert error.value.status_code == 400
    assert "must equal" in error.value.detail
