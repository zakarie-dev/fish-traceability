from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Catch,
    Consignment,
    ConsignmentLot,
    Lot,
    LotLink,
    ProcessingStep,
    Species,
    TemperatureLog,
    Vessel,
)


class LotRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_lot(self, lot_id: UUID, *, for_update: bool = False) -> Lot | None:
        statement = select(Lot).where(Lot.id == lot_id)
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_lot_by_code(self, lot_code: str) -> Lot | None:
        return self._db.scalar(select(Lot).where(Lot.lot_code == lot_code))

    def get_lots_for_update(self, lot_ids: list[UUID]) -> list[Lot]:
        statement = (
            select(Lot)
            .where(Lot.id.in_(lot_ids))
            .order_by(Lot.id)
            .with_for_update()
        )
        return list(self._db.scalars(statement))

    def add_lots(self, lots: list[Lot]) -> None:
        self._db.add_all(lots)

    def add_links(self, links: list[LotLink]) -> None:
        self._db.add_all(links)

    def get_ancestor_ids(self, lot_id: UUID) -> list[UUID]:
        statement = text(
            """
            WITH RECURSIVE ancestors(id, path) AS (
                SELECT lot.id, ARRAY[lot.id]
                FROM lots AS lot
                WHERE lot.id = :lot_id

                UNION ALL

                SELECT parent.id, ancestors.path || parent.id
                FROM ancestors
                JOIN lot_links AS edge ON edge.child_lot_id = ancestors.id
                JOIN lots AS parent ON parent.id = edge.parent_lot_id
                WHERE NOT parent.id = ANY(ancestors.path)
            )
            SELECT DISTINCT id
            FROM ancestors
            """
        )
        return list(self._db.scalars(statement, {"lot_id": lot_id}).all())

    def get_descendant_ids(self, lot_id: UUID) -> list[UUID]:
        statement = text(
            """
            WITH RECURSIVE descendants(id, path) AS (
                SELECT lot.id, ARRAY[lot.id]
                FROM lots AS lot
                WHERE lot.id = :lot_id

                UNION ALL

                SELECT child.id, descendants.path || child.id
                FROM descendants
                JOIN lot_links AS edge ON edge.parent_lot_id = descendants.id
                JOIN lots AS child ON child.id = edge.child_lot_id
                WHERE NOT child.id = ANY(descendants.path)
            )
            SELECT DISTINCT id
            FROM descendants
            """
        )
        return list(self._db.scalars(statement, {"lot_id": lot_id}).all())

    def get_lots(self, lot_ids: list[UUID]) -> list[Lot]:
        if not lot_ids:
            return []
        return list(self._db.scalars(select(Lot).where(Lot.id.in_(lot_ids))))

    def get_species(self, species_ids: list[UUID]) -> list[Species]:
        if not species_ids:
            return []
        return list(self._db.scalars(select(Species).where(Species.id.in_(species_ids))))

    def get_catches(self, catch_ids: list[UUID]) -> list[Catch]:
        if not catch_ids:
            return []
        return list(self._db.scalars(select(Catch).where(Catch.id.in_(catch_ids))))

    def get_vessels(self, vessel_ids: list[UUID]) -> list[Vessel]:
        if not vessel_ids:
            return []
        return list(self._db.scalars(select(Vessel).where(Vessel.id.in_(vessel_ids))))

    def get_processing_steps(self, lot_ids: list[UUID]) -> list[ProcessingStep]:
        if not lot_ids:
            return []
        statement = (
            select(ProcessingStep)
            .where(ProcessingStep.lot_id.in_(lot_ids))
            .order_by(ProcessingStep.id)
        )
        return list(self._db.scalars(statement))

    def get_temperature_logs(self, lot_ids: list[UUID]) -> list[TemperatureLog]:
        if not lot_ids:
            return []
        statement = (
            select(TemperatureLog)
            .where(TemperatureLog.lot_id.in_(lot_ids))
            .order_by(TemperatureLog.recorded_at)
        )
        return list(self._db.scalars(statement))

    def get_consignments(self, lot_ids: list[UUID]) -> list[Consignment]:
        if not lot_ids:
            return []
        statement = (
            select(Consignment)
            .join(
                ConsignmentLot,
                ConsignmentLot.consignment_id == Consignment.id,
            )
            .where(ConsignmentLot.lot_id.in_(lot_ids))
            .distinct()
            .order_by(Consignment.id)
        )
        return list(self._db.scalars(statement))
