from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Vessel
from app.repositories.vessel_repository import VesselRepository
from app.schemas import VesselCreate


class VesselService:
    def __init__(self, db: Session) -> None:
        self._vessels = VesselRepository(db)

    def create_vessel(self, vessel_data: VesselCreate, actor_id: UUID) -> Vessel:
        return self._vessels.create(vessel_data, actor_id)
