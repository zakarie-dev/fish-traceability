from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import User
from app.schemas import LotTraceResponse, RecallResponse, UserRole
from app.services.traceability_service import TraceabilityService

router = APIRouter(tags=["traceability"])


@router.get("/trace/{lot_code}", response_model=LotTraceResponse)
def trace_lot(
    lot_code: str,
    db: Session = Depends(get_db),
) -> LotTraceResponse:
    """Return full backward and forward traceability for a lot code."""
    return TraceabilityService(db).get_trace(lot_code)


@router.post(
    "/recall/{lot_id}",
    response_model=RecallResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def recall_lot(
    lot_id: UUID,
    db: Session = Depends(get_db),
) -> RecallResponse:
    """Recall a lot and all descendants and linked consignments."""
    return TraceabilityService(db).recall_lot(lot_id)
