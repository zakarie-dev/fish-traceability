from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.lot_service import LotService


def test_merge_rejects_different_species(monkeypatch):
    first, second = uuid4(), uuid4()
    lots = [
        SimpleNamespace(id=first, species_id=uuid4(), current_weight=Decimal("2")),
        SimpleNamespace(id=second, species_id=uuid4(), current_weight=Decimal("3")),
    ]

    class FakeLotRepository:
        def __init__(self, _db):
            pass

        def get_lots_for_update(self, _lot_ids):
            return lots

    monkeypatch.setattr("app.services.lot_service.LotRepository", FakeLotRepository)
    session = SimpleNamespace(begin=lambda: nullcontext())

    with pytest.raises(HTTPException) as error:
        LotService(session).merge_lots([first, second])

    assert error.value.status_code == 400
    assert "same species" in error.value.detail
