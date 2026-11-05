from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Vessel
from app.schemas import VesselCreate
from app.services.audit_service import record_audit_event


class VesselRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, vessel_data: VesselCreate, actor_id: UUID) -> Vessel:
        vessel = Vessel(**vessel_data.model_dump())
        self._db.add(vessel)
        try:
            self._db.flush()
            record_audit_event(
                self._db,
                user_id=actor_id,
                action="vessel.create",
                entity_id=vessel.id,
            )
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        self._db.refresh(vessel)
        return vessel
