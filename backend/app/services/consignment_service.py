from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Consignment,
    ConsignmentLot,
    Inspection,
    Lot,
    TemperatureLog,
)
from app.services.audit_service import record_audit_event


def eligible_lots_statement() -> Select[tuple[Lot]]:
    """Build a query for unassigned, available lots with a current passing inspection."""
    inspection_order = (Inspection.inspected_at.desc(), Inspection.id.desc())
    latest_inspection_at = (
        select(Inspection.inspected_at)
        .where(Inspection.lot_id == Lot.id)
        .order_by(*inspection_order)
        .limit(1)
        .scalar_subquery()
    )
    latest_inspection_passed = (
        select(Inspection.passed)
        .where(Inspection.lot_id == Lot.id)
        .order_by(*inspection_order)
        .limit(1)
        .scalar_subquery()
    )
    latest_breach_at = (
        select(func.max(TemperatureLog.recorded_at))
        .where(
            TemperatureLog.lot_id == Lot.id,
            TemperatureLog.is_breach.is_(True),
        )
        .scalar_subquery()
    )
    already_assigned = exists(
        select(ConsignmentLot.lot_id).where(ConsignmentLot.lot_id == Lot.id)
    )
    return (
        select(Lot)
        .where(
            Lot.status == "Available",
            latest_inspection_passed.is_(True),
            or_(latest_breach_at.is_(None), latest_inspection_at > latest_breach_at),
            ~already_assigned,
        )
        .order_by(Lot.lot_code)
    )


class ConsignmentService:
    """Create consignments from lots that satisfy export eligibility rules."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_eligible_lots(self) -> list[Lot]:
        """Return available lots whose latest inspection passes any breach."""
        return list(self._db.scalars(eligible_lots_statement()))

    def create_consignment(
        self,
        *,
        lot_ids: list[UUID],
        buyer_name: str,
        destination_country: str,
        shipping_date: date,
        container_number: str,
        actor_id: UUID,
    ) -> UUID:
        """Persist a consignment and its eligible lots as one transaction."""
        if not lot_ids or len(set(lot_ids)) != len(lot_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select one or more unique eligible lots.",
            )

        with self._db.begin():
            lots = list(
                self._db.scalars(
                    eligible_lots_statement()
                    .where(Lot.id.in_(lot_ids))
                    .with_for_update()
                )
            )
            if len(lots) != len(lot_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Every selected lot must be available, unassigned, and have "
                        "a passing inspection after its latest temperature breach."
                    ),
                )

            consignment_id = uuid4()
            consignment = Consignment(
                id=consignment_id,
                buyer_name=buyer_name,
                destination_country=destination_country,
                shipping_date=shipping_date,
                container_number=container_number,
            )
            self._db.add(consignment)
            self._db.add_all(
                [
                    ConsignmentLot(
                        consignment_id=consignment_id,
                        lot_id=lot.id,
                    )
                    for lot in lots
                ]
            )
            record_audit_event(
                self._db,
                user_id=actor_id,
                action="consignment.create",
                entity_id=consignment_id,
            )
        return consignment_id
