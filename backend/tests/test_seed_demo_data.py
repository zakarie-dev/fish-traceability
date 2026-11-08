from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Catch,
    Consignment,
    ConsignmentLot,
    Inspection,
    LandingSite,
    Lot,
    LotLink,
    PaymentTransaction,
    ProcessingStep,
    SMSOutbox,
    Species,
    TemperatureLog,
    User,
    Vessel,
)
from seed_demo_data import seed_demo_data


def test_seed_demo_data_creates_coherent_workflow_and_is_repeat_safe():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                User(
                    id=uuid4(),
                    email=f"{role.lower()}@seed.test",
                    hashed_password="unused-test-hash",
                    role=role,
                )
                for role in (
                    "Admin",
                    "Officer",
                    "Processor",
                    "Inspector",
                )
            ]
        )
        db.commit()

        assert seed_demo_data(db) is True
        assert seed_demo_data(db) is False

        assert db.scalar(select(func.count(LandingSite.id))) == 4
        assert db.scalar(select(func.count(Vessel.id))) == 3
        assert db.scalar(select(func.count(Species.id))) == 3

        catches = list(
            db.scalars(
                select(Catch).where(Catch.catch_area.like("Demo showcase catch %"))
            )
        )
        assert len(catches) == 15
        assert all(
            date.today() - timedelta(days=90) <= catch.catch_date <= date.today()
            for catch in catches
        )

        lots = list(
            db.scalars(select(Lot).where(Lot.lot_code.like("LOT-DEMO-SHOWCASE-%")))
        )
        assert len(lots) == 26
        parent_lots = [
            lot
            for lot in lots
            if len(lot.lot_code.rsplit("-", 1)[-1]) == 3
            and lot.lot_code.rsplit("-", 1)[-1].isdigit()
        ]
        assert len(parent_lots) == 15
        assert all(
            Decimal("50") <= lot.current_weight <= Decimal("500")
            for lot in parent_lots
        )

        split_parents = [lot for lot in parent_lots if lot.status == "Split"]
        assert len(split_parents) == 5
        for parent in split_parents:
            children = list(
                db.scalars(
                    select(Lot)
                    .join(LotLink, LotLink.child_lot_id == Lot.id)
                    .where(LotLink.parent_lot_id == parent.id)
                )
            )
            assert len(children) == 2
            assert sum(
                (child.current_weight for child in children), Decimal("0")
            ) == parent.current_weight

        assert db.scalar(select(func.count(ProcessingStep.id))) == 5
        temperatures = list(db.scalars(select(TemperatureLog)))
        assert len(temperatures) == 15
        assert sum(log.is_breach for log in temperatures) == 2
        assert sum(
            log.temperature_type == "Chilled"
            and log.temp_celsius == Decimal("8.00")
            and log.is_breach
            for log in temperatures
        ) == 2
        assert sum(
            log.temperature_type == "Frozen"
            and log.temp_celsius == Decimal("-20.00")
            and not log.is_breach
            for log in temperatures
        ) == 13

        inspections = list(db.scalars(select(Inspection)))
        assert len(inspections) == 6
        assert sum(inspection.passed for inspection in inspections) == 4
        assert sum(not inspection.passed for inspection in inspections) == 2

        consignments = list(db.scalars(select(Consignment)))
        assert len(consignments) == 3
        assignments = list(db.scalars(select(ConsignmentLot)))
        assert len(assignments) == 3
        for assignment in assignments:
            inspection = db.scalar(
                select(Inspection)
                .where(
                    Inspection.lot_id == assignment.lot_id,
                    Inspection.passed.is_(True),
                )
            )
            temperature = db.scalar(
                select(TemperatureLog).where(
                    TemperatureLog.lot_id == assignment.lot_id
                )
            )
            assert inspection is not None
            assert temperature is not None and not temperature.is_breach

        assert db.scalar(select(func.count(PaymentTransaction.id))) == 3
        assert db.scalar(select(func.count(SMSOutbox.id))) == 5
        assert db.scalar(select(func.count(LotLink.parent_lot_id))) == 12

    engine.dispose()
