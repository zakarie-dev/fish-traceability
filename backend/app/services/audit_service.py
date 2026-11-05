from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit_event(
    db: Session,
    *,
    user_id: UUID,
    action: str,
    entity_id: UUID | None = None,
) -> None:
    """Queue an audit entry in the caller's transaction."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_id=entity_id,
        )
    )
