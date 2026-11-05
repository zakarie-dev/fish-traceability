from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Catch, Consignment, LandingSite, Lot, Species, TemperatureLog


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_available_lot_weight(self) -> Decimal:
        statement = select(
            func.coalesce(func.sum(Lot.current_weight), 0)
        ).where(Lot.status == "Available")
        return self._db.scalar(statement) or Decimal("0")

    def count_consignments(self) -> int:
        statement = select(func.count(Consignment.id)).where(
            Consignment.status == "Active"
        )
        return self._db.scalar(statement) or 0

    def count_temperature_breaches(self) -> int:
        statement = select(func.count(TemperatureLog.id)).where(
            TemperatureLog.is_breach.is_(True)
        )
        return self._db.scalar(statement) or 0

    def get_available_weight_by_species(self) -> list[tuple[str, Decimal]]:
        statement = (
            select(Species.name, func.sum(Lot.current_weight))
            .join(Lot, Lot.species_id == Species.id)
            .where(Lot.status == "Available")
            .group_by(Species.id, Species.name)
            .order_by(Species.name)
        )
        return list(self._db.execute(statement).all())

    def get_available_weight_by_landing_site(self) -> list[tuple[str, Decimal]]:
        statement = (
            select(LandingSite.name, func.sum(Lot.current_weight))
            .join(Catch, Catch.landing_site_id == LandingSite.id)
            .join(Lot, Lot.catch_id == Catch.id)
            .where(Lot.status == "Available")
            .group_by(LandingSite.id, LandingSite.name)
            .order_by(LandingSite.name)
        )
        return list(self._db.execute(statement).all())

    def get_recent_lots(
        self, limit: int = 5
    ) -> list[tuple[UUID, str, str, Decimal, str]]:
        statement = (
            select(
                Lot.id,
                Lot.lot_code,
                Species.name,
                Lot.current_weight,
                Lot.status,
            )
            .join(Species, Species.id == Lot.species_id)
            .outerjoin(Catch, Catch.id == Lot.catch_id)
            .order_by(
                Catch.landing_date.desc().nullslast(),
                Lot.lot_code.desc(),
            )
            .limit(limit)
        )
        return list(self._db.execute(statement).all())
