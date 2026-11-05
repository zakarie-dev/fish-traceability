from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.lot_service import LotService


def test_merge_same_species_sums_weights(monkeypatch):
    species_id = uuid4()
    first, second = uuid4(), uuid4()
    lots = [
        SimpleNamespace(
            id=first,
            species_id=species_id,
            current_weight=Decimal("2.25"),
            status="Available",
        ),
        SimpleNamespace(
            id=second,
            species_id=species_id,
            current_weight=Decimal("3.75"),
            status="Available",
        ),
    ]
    session = SimpleNamespace(begin=lambda: nullcontext(), added=[])

    class FakeLotRepository:
        def __init__(self, _db):
            pass

        def get_lots_for_update(self, _lot_ids):
            return lots

        def add_lots(self, new_lots):
            session.added.extend(new_lots)

        def add_links(self, links):
            session.added.extend(links)

    monkeypatch.setattr("app.services.lot_service.LotRepository", FakeLotRepository)

    merged_id = LotService(session).merge_lots([first, second])

    merged = session.added[0]
    assert merged.id == merged_id
    assert merged.current_weight == Decimal("6.00")
    assert all(lot.status == "Merged" for lot in lots)
