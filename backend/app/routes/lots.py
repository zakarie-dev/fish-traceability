from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LotMergeRequest
from app.services.lot_service import LotService

router = APIRouter(prefix="/lots", tags=["lots"])


@router.post("/merge")
def merge_lots(
    request: LotMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, UUID]:
    """Merge eligible lots and audit the authenticated user who initiated it."""
    if current_user.role not in {"Admin", "Processor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processor role required",
        )
    actor_id = current_user.id
    db.rollback()
    merged_lot_id = LotService(db).merge_lots(
        request.lot_ids,
        actor_id=actor_id,
    )
    return {"merged_lot_id": merged_lot_id}
