from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import PUBLIC_TRACE_BASE_URL
from app.database import get_db
from app.dependencies import require_role
from app.models import User
from app.schemas import UserRole
from app.services.certificate_service import generate_certificate_pdf

router = APIRouter(prefix="/consignments", tags=["certificates"])


@router.get(
    "/{consignment_id}/certificate.pdf",
    response_class=Response,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def export_certificate(
    consignment_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Download a PDF traceability certificate for a consignment."""
    pdf = generate_certificate_pdf(db, consignment_id, PUBLIC_TRACE_BASE_URL)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="certificate-{consignment_id}.pdf"'
            )
        },
    )
