from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    get_jwt_secret_key,
)
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas import TokenResponse, UserRole
from app.security import verify_password


class AuthService:
    def __init__(self, db: Session) -> None:
        self._users = UserRepository(db)

    def authenticate(self, email: str, password: str) -> TokenResponse:
        user = self._users.get_by_email(email.strip().lower())
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            role = UserRole(user.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account has an unsupported role",
            ) from exc

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
        token = jwt.encode(
            {"sub": str(user.id), "role": role.value, "exp": expires_at},
            get_jwt_secret_key(),
            algorithm=JWT_ALGORITHM,
        )
        return TokenResponse(access_token=token)

    def get_current_user(self, token: str) -> User:
        user_id, token_role = decode_access_token(token)
        user = self._users.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User for this access token no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            current_role = UserRole(user.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account has an unsupported role",
            ) from exc
        if current_role != token_role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token role is no longer current",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


def decode_access_token(token: str) -> tuple[UUID, UserRole]:
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret_key(),
            algorithms=[JWT_ALGORITHM],
        )
        subject = payload.get("sub")
        role_claim = payload.get("role")
        if not isinstance(subject, str) or not isinstance(role_claim, str):
            raise ValueError("Token is missing its subject or role")
        user_id = UUID(subject)
        role = UserRole(role_claim)
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return user_id, role
