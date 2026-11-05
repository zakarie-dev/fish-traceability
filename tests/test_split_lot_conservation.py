from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.lot_service import LotService


class FakeSession:
    def __init__(self):
        self.added = []

    def begin(self):
        return nullcontext()

    def add(self, item):
        self.added.append(item)


def test_split_child_weights_and_loss_equal_parent(monkeypatch):
    parent = SimpleNamespace(
        id=uuid4(),
        current_weight=Decimal("100.00"),
        catch_id=uuid4(),
        species_id=uuid4(),
        status="Available",
    )
    session = FakeSession()

    class FakeLotRepository:
        def __init__(self, _db):
            pass

        def get_lot(self, _lot_id, for_update=False):
            return parent

        def add_lots(self, lots):
            session.added.extend(lots)

        def add_links(self, links):
            session.added.extend(links)

    monkeypatch.setattr("app.services.lot_service.LotRepository", FakeLotRepository)

    child_ids = LotService(session).split_lot(parent.id, [40, 55], 5)

    children = [item for item in session.added if hasattr(item, "current_weight")]
    assert len(child_ids) == 2
    assert sum((child.current_weight for child in children), Decimal("0")) + Decimal(
        "5.00"
    ) == parent.current_weight
    assert parent.status == "Split"
