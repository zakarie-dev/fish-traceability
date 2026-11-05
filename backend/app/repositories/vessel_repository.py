from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Vessel
from app.schemas import VesselCreate


class VesselRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, vessel_data: VesselCreate) -> Vessel:
        vessel = Vessel(**vessel_data.model_dump())
        self._db.add(vessel)
        try:
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        self._db.refresh(vessel)
        return vessel
