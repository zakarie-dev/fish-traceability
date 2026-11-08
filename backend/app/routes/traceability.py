from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
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
)
def recall_lot(
    lot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecallResponse:
    """Recall a lot and all descendants and linked consignments."""
    if current_user.role not in {UserRole.ADMIN.value, UserRole.INSPECTOR.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inspector role required",
        )
    return TraceabilityService(db).recall_lot(lot_id)
