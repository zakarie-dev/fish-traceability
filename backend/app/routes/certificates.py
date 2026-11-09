from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import AuthenticatedHTMLUser, require_html_user
from app.services.audit_service import record_audit_event
from app.services.certificate_service import generate_certificate_pdf

router = APIRouter(prefix="/consignments", tags=["certificates"])


@router.get(
    "/{consignment_id}/certificate.pdf",
    response_class=Response,
)
def export_certificate(
    consignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Download a PDF traceability certificate for a consignment."""
    if current_user.role not in {"Admin", "Exporter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Exporter role required",
        )
    pdf = generate_certificate_pdf(db, consignment_id)
    record_audit_event(
        db,
        user_id=current_user.id,
        action="certificate.issue",
        entity_id=consignment_id,
    )
    db.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="certificate-{consignment_id}.pdf"'
            )
        },
    )
