from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

from app.services.traceability_service import TraceabilityService


def test_recall_marks_starting_lot_descendants_and_buyers(monkeypatch):
    root_id, child_id, grandchild_id = uuid4(), uuid4(), uuid4()
    lots = [
        SimpleNamespace(id=root_id),
        SimpleNamespace(id=child_id),
        SimpleNamespace(id=grandchild_id),
    ]
    consignment = SimpleNamespace(
        id=uuid4(), buyer_name="Buyer", destination_country="Somalia"
    )
    updated = []

    class FakeRepository:
        def __init__(self, _db):
            pass

        def get_lots_for_update(self, lot_ids):
            return [lot for lot in lots if lot.id in lot_ids]

        def get_descendant_ids(self, _lot_id):
            return [root_id, child_id, grandchild_id]

        def get_consignments(self, _lot_ids):
            return [consignment]

    class FakeSession:
        def begin(self):
            return nullcontext()

        def execute(self, statement):
            updated.append(statement)

    monkeypatch.setattr(
        "app.services.traceability_service.LotRepository", FakeRepository
    )
    result = TraceabilityService(FakeSession()).recall_lot(root_id)

    assert set(result.affected_lot_ids) == {root_id, child_id, grandchild_id}
    assert result.affected_buyers[0].buyer_name == "Buyer"
    assert result.affected_buyers[0].destination_country == "Somalia"
    assert len(updated) == 2
