from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserRole
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedHTMLUser:
    id: UUID
    role: str


def require_html_user(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthenticatedHTMLUser:
    """Authenticate browser pages using a session cookie or Bearer header.

    Browser requests are redirected to the login page when credentials are
    missing, malformed, expired, or no longer associated with an active user.
    """
    token = request.cookies.get("access_token")
    if not token:
        authorization = request.headers.get("Authorization", "")
        scheme, separator, credentials = authorization.partition(" ")
        if separator and scheme.lower() == "bearer":
            token = credentials.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    try:
        current_user = AuthService(db).get_current_user(token)
        authenticated_user = AuthenticatedHTMLUser(
            id=current_user.id,
            role=current_user.role,
        )
        db.rollback()
        return authenticated_user
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthService(db).get_current_user(credentials.credentials)


def require_role(required_role: UserRole) -> Callable[..., User]:
    def role_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role != required_role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{required_role.value} role required",
            )
        return current_user

    return role_dependency
