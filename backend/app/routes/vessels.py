from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import User, Vessel
from app.schemas import UserRole, VesselCreate, VesselResponse
from app.services.vessel_service import VesselService

router = APIRouter(prefix="/vessels", tags=["vessels"])


@router.post(
    "",
    response_model=VesselResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_vessel(
    vessel_data: VesselCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> Vessel:
    return VesselService(db).create_vessel(vessel_data, admin.id)
