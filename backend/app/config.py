from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
PUBLIC_TRACE_BASE_URL = os.getenv(
    "PUBLIC_TRACE_BASE_URL", "http://localhost:8000/trace"
).rstrip("/")


def get_database_url() -> str:
    """Return the configured PostgreSQL URL or fail with actionable guidance."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to backend/.env before starting the API."
        )
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    return database_url


def get_jwt_secret_key() -> str:
    """Return the configured JWT signing key or fail with actionable guidance."""
    secret_key = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")
    if not secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Add a strong random key to backend/.env."
        )
    return secret_key
