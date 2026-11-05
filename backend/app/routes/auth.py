import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.schemas import LoginRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


@router.get("/login", include_in_schema=False)
def login_form_redirect() -> RedirectResponse:
    """Send direct visits to the form endpoint to the HTML login page."""
    return RedirectResponse(
        url="/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/login", response_model=None)
async def login(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Authenticate form or API credentials and issue the appropriate response."""
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0]
    is_html_form = content_type in {
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    }

    try:
        if is_html_form:
            form = await request.form()
            credentials = LoginRequest(
                email=str(form.get("email", "")),
                password=str(form.get("password", "")),
            )
        else:
            payload = await request.json()
            credentials = LoginRequest.model_validate(payload)
    except (ValidationError, ValueError):
        if is_html_form:
            return RedirectResponse(
                url="/login?error=invalid",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email and password are required",
        ) from None

    try:
        token = AuthService(db).authenticate(credentials.email, credentials.password)
    except HTTPException as exc:
        if is_html_form and exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(
                url="/login?error=invalid",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise
    except SQLAlchemyError as exc:
        logger.exception("Login failed because the authentication database is unavailable")
        if is_html_form:
            return RedirectResponse(
                url="/login?error=unavailable",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from exc

    if not is_html_form:
        return JSONResponse(content=token.model_dump())

    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key="access_token",
        value=token.access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response
