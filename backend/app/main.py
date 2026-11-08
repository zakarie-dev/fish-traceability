from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Query, status
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters import MockPaymentAdapter, MockSMSAdapter, PaymentProvider
from app.config import PUBLIC_TRACE_BASE_URL
from app.database import get_db
from app.dependencies import AuthenticatedHTMLUser, require_html_user
from app.models import (
    Catch,
    Consignment,
    ConsignmentLot,
    Inspection,
    LandingSite,
    Lot,
    PaymentTransaction,
    ProcessingStep,
    Species,
    SMSOutbox,
    TemperatureLog,
    User,
    Vessel,
)
from app.routes.auth import router as auth_router
from app.routes.certificates import router as certificates_router
from app.routes.lots import router as lots_router
from app.routes.traceability import router as traceability_router
from app.routes.vessels import router as vessels_router
from app.schemas import VesselCreate
from app.services.consignment_service import ConsignmentService
from app.services.dashboard_service import DashboardService
from app.services.lot_service import LotService
from app.services.traceability_service import TraceabilityService
from app.services.vessel_service import VesselService
from app.translations import TRANSLATIONS, get_translations

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Fish Traceability API")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _selected_language(request: Request) -> str:
    requested_language = request.query_params.get("lang")
    if requested_language is not None and requested_language in TRANSLATIONS:
        return requested_language
    cookie_language = request.cookies.get("lang")
    if cookie_language is not None and cookie_language in TRANSLATIONS:
        return cookie_language
    return "en"


def _set_language_cookie(response: HTMLResponse, language: str) -> None:
    response.set_cookie(
        key="lang",
        value=language,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
    )


def _render_landing_sites(
    request: Request,
    db: Session,
    current_user: AuthenticatedHTMLUser,
    *,
    error: str | None = None,
    form_data: dict[str, str] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    language = _selected_language(request)
    translations = get_translations(language)
    response = templates.TemplateResponse(
        request=request,
        name="landing_sites.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "landing-sites",
            "current_user": current_user,
            "landing_sites": [
                {
                    "name": site.name,
                    "region": site.region,
                    "latitude": str(site.gps_lat) if site.gps_lat is not None else "—",
                    "longitude": str(site.gps_lng) if site.gps_lng is not None else "—",
                    "status": (
                        translations["site_active"]
                        if site.is_active
                        else translations["site_inactive"]
                    ),
                }
                for site in db.scalars(select(LandingSite).order_by(LandingSite.name))
            ],
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


def _render_catch_form(
    request: Request,
    db: Session,
    *,
    form_data: dict[str, str] | None = None,
    error: str | None = None,
    success: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    language = _selected_language(request)
    translations = get_translations(language)
    response = templates.TemplateResponse(
        request=request,
        name="catch.html",
        context={
            "language": language,
            "t": translations,
            "vessels": list(db.scalars(select(Vessel).order_by(Vessel.name))),
            "species": list(db.scalars(select(Species).order_by(Species.name))),
            "landing_sites": list(
                db.scalars(select(LandingSite).order_by(LandingSite.name))
            ),
            "officers": list(
                db.scalars(
                    select(User)
                    .where(User.role == "Officer")
                    .order_by(User.email)
                )
            ),
            "form_data": form_data or {},
            "error": error,
            "success": success,
            "today": date.today().isoformat(),
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


def _render_lot_detail(
    request: Request,
    db: Session,
    lot_id: UUID,
    current_user: AuthenticatedHTMLUser,
    *,
    error: str | None = None,
    form_data: dict[str, str] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found",
        )

    species = db.get(Species, lot.species_id)
    temperature_logs = list(
        db.scalars(
            select(TemperatureLog)
            .where(TemperatureLog.lot_id == lot_id)
            .order_by(TemperatureLog.recorded_at.desc())
        )
    )
    inspection_rows = list(
        db.execute(
            select(Inspection, User.email)
            .join(User, User.id == Inspection.inspector_id)
            .where(Inspection.lot_id == lot_id)
            .order_by(Inspection.inspected_at.desc(), Inspection.id.desc())
        )
    )
    processing_steps = list(
        db.scalars(
            select(ProcessingStep)
            .where(ProcessingStep.lot_id == lot_id)
            .order_by(ProcessingStep.id.desc())
        )
    )
    latest_breach_at = db.scalar(
        select(func.max(TemperatureLog.recorded_at)).where(
            TemperatureLog.lot_id == lot_id,
            TemperatureLog.is_breach.is_(True),
        )
    )
    latest_pass_at = db.scalar(
        select(func.max(Inspection.inspected_at)).where(
            Inspection.lot_id == lot_id,
            Inspection.passed.is_(True),
        )
    )
    open_temperature_breach = (
        latest_breach_at is not None
        and (latest_pass_at is None or latest_pass_at <= latest_breach_at)
    )
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="lot_detail.html",
        context={
            "language": language,
            "t": get_translations(language),
            "current_user": current_user,
            "lot": lot,
            "species_name": species.name if species is not None else "Unknown",
            "temperature_logs": temperature_logs,
            "processing_steps": processing_steps,
            "open_temperature_breach": open_temperature_breach,
            "latest_breach_at": latest_breach_at,
            "inspections": [
                {"inspection": inspection, "inspector_email": email}
                for inspection, email in inspection_rows
            ],
            "inspectors": list(
                db.scalars(
                    select(User)
                    .where(User.role == "Inspector")
                    .order_by(User.email)
                )
            ),
            "error": error,
            "success": request.query_params.get("success"),
            "warning": request.query_params.get("warning"),
            "form_data": form_data or {},
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


def _render_vessels(
    request: Request,
    db: Session,
    current_user: AuthenticatedHTMLUser,
    *,
    error: str | None = None,
    form_data: dict[str, str] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    language = _selected_language(request)
    translations = get_translations(language)
    vessels = list(db.scalars(select(Vessel).order_by(Vessel.name)))
    rows = [
        {
            "name": vessel.name,
            "registration": vessel.reg_number,
            "license": vessel.license_number,
            "expiry": vessel.license_expiry.isoformat(),
            "port": vessel.home_port,
            "gear": vessel.gear_type,
        }
        for vessel in vessels
    ]
    response = templates.TemplateResponse(
        request=request,
        name="vessels.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "vessels",
            "current_user": current_user,
            "vessels": rows,
            "error": error,
            "form_data": form_data or {},
            "created": request.query_params.get("created"),
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


def _render_merge_lots(
    request: Request,
    db: Session,
    current_user: AuthenticatedHTMLUser,
    *,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(Species.name, Lot.id, Lot.lot_code, Lot.current_weight)
        .join(Lot, Lot.species_id == Species.id)
        .where(Lot.status == "Available")
        .order_by(Species.name, Lot.lot_code)
    )
    grouped_lots: dict[str, list[dict[str, str]]] = {}
    for species_name, lot_id, lot_code, weight in db.execute(statement).all():
        grouped_lots.setdefault(species_name, []).append(
            {
                "id": str(lot_id),
                "lot_code": lot_code,
                "weight": f"{weight:,.2f}",
            }
        )
    groups = [
        {"species": species_name, "lots": lots}
        for species_name, lots in grouped_lots.items()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="merge_lots.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "lots",
            "current_user": current_user,
            "groups": groups,
            "error": error,
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


def _render_consignment_form(
    request: Request,
    db: Session,
    *,
    form_data: dict[str, object] | None = None,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="create_consignment.html",
        context={
            "language": language,
            "t": get_translations(language),
            "active_page": "consignments",
            "lots": ConsignmentService(db).get_eligible_lots(),
            "form_data": form_data or {},
            "error": error,
            "today": date.today().isoformat(),
        },
        status_code=status_code,
    )
    _set_language_cookie(response, language)
    return response


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "language": language,
            "t": get_translations(language),
            "error": {
                "invalid": "Invalid email or password.",
                "unavailable": (
                    "The database cannot be reached. Check the DATABASE_URL host in "
                    "backend/.env against your Supabase project's Database connection "
                    "settings, then restart the app."
                ),
            }.get(request.query_params.get("error")),
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get("/catches", response_class=HTMLResponse, include_in_schema=False)
def catch_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the browser form used to record a catch and create its initial lot."""
    if current_user.role != "Officer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officer role required",
        )
    return _render_catch_form(
        request,
        db,
        success=request.query_params.get("success"),
    )


@app.post(
    "/catches",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def create_catch_from_form(
    request: Request,
    vessel_id: str = Form(...),
    species_id: str = Form(...),
    weight: str = Form(...),
    catch_area: str = Form(...),
    catch_date: str = Form(...),
    landing_date: str = Form(...),
    landing_site_id: str = Form(...),
    officer_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Save a catch and corresponding available lot from the HTML form."""
    if current_user.role != "Officer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officer role required",
        )
    form_data = {
        "vessel_id": vessel_id,
        "species_id": species_id,
        "weight": weight,
        "catch_area": catch_area,
        "catch_date": catch_date,
        "landing_date": landing_date,
        "landing_site_id": landing_site_id,
        "officer_id": officer_id,
    }

    try:
        selected_vessel_id = UUID(vessel_id)
        selected_species_id = UUID(species_id)
        selected_site_id = UUID(landing_site_id)
        selected_officer_id = UUID(officer_id)
        selected_catch_date = date.fromisoformat(catch_date)
        selected_landing_date = date.fromisoformat(landing_date)
        catch_weight = Decimal(weight)
        if not catch_weight.is_finite() or catch_weight <= 0:
            raise ValueError("Weight must be greater than zero.")
        if catch_weight.quantize(Decimal("0.01")) != catch_weight:
            raise ValueError("Weight must have no more than two decimal places.")
        if catch_weight >= Decimal("100000000"):
            raise ValueError("Weight is outside the supported range.")
    except (InvalidOperation, ValueError):
        return _render_catch_form(
            request,
            db,
            form_data=form_data,
            error="Enter valid selections, dates, and a positive weight with up to two decimals.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    cleaned_area = catch_area.strip()
    if not cleaned_area:
        return _render_catch_form(
            request,
            db,
            form_data=form_data,
            error="Catch area is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if selected_landing_date < selected_catch_date:
        return _render_catch_form(
            request,
            db,
            form_data=form_data,
            error="Landing date cannot be earlier than catch date.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    validation_error = None
    with db.begin():
        vessel = db.get(Vessel, selected_vessel_id)
        species = db.get(Species, selected_species_id)
        landing_site = db.get(LandingSite, selected_site_id)
        officer = db.get(User, selected_officer_id)
        if vessel is None or species is None or landing_site is None:
            validation_error = "Select a vessel, species, and landing site from the list."
        elif officer is None or officer.role != "Officer":
            validation_error = "Select an authorized officer from the list."
        else:
            catch_record = Catch(
                id=uuid4(),
                vessel_id=vessel.id,
                officer_id=officer.id,
                landing_site_id=landing_site.id,
                catch_date=selected_catch_date,
                landing_date=selected_landing_date,
                catch_area=cleaned_area,
                gear_used=vessel.gear_type,
            )
            lot_id = uuid4()
            lot = Lot(
                id=lot_id,
                lot_code=f"LOT-{lot_id.hex.upper()}",
                catch_id=catch_record.id,
                species_id=species.id,
                current_weight=catch_weight,
                status="Available",
            )
            db.add_all([catch_record, lot])

    if validation_error is not None:
        return _render_catch_form(
            request,
            db,
            form_data=form_data,
            error=validation_error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/catches?success=catch", status_code=303)


@app.get(
    "/lots/merge-selection",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def merge_lots_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    if current_user.role not in {"Admin", "Processor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processor role required",
        )
    return _render_merge_lots(request, db, current_user)


@app.post(
    "/lots/merge-form",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def merge_lots_from_form(
    request: Request,
    lot_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    if current_user.role not in {"Admin", "Processor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processor role required",
        )
    try:
        selected_lot_ids = [UUID(lot_id) for lot_id in lot_ids]
    except ValueError:
        return _render_merge_lots(
            request,
            db,
            current_user,
            error="Select valid lots to merge.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        LotService(db).merge_lots(
            selected_lot_ids,
            actor_id=current_user.id,
        )
    except HTTPException as exc:
        return _render_merge_lots(
            request,
            db,
            current_user,
            error=str(exc.detail),
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url="/lots?merged=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/lots/{lot_id}", response_class=HTMLResponse, include_in_schema=False)
def lot_detail_page(
    lot_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render lot details and the split, temperature, and inspection forms."""
    return _render_lot_detail(request, db, lot_id, current_user)


@app.post(
    "/lots/{lot_id}/recall",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def recall_lot_from_form(
    lot_id: UUID,
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
    db: Session = Depends(get_db),
) -> Response:
    if current_user.role not in {"Admin", "Inspector"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inspector role required",
        )
    TraceabilityService(db).recall_lot(lot_id)
    return RedirectResponse(
        url=f"/lots/{lot_id}?success=recall",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post(
    "/lots/{lot_id}/split",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def split_lot_from_form(
    lot_id: UUID,
    request: Request,
    child_weights: str = Form(...),
    loss_weight: str = Form(...),
    loss_reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Split a lot using comma- or newline-separated child weights."""
    if current_user.role != "Processor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processor role required",
        )
    form_data = {
        "child_weights": child_weights,
        "loss_weight": loss_weight,
        "loss_reason": loss_reason,
    }
    try:
        raw_weights = child_weights.replace("\n", ",").split(",")
        weights = [float(Decimal(value.strip())) for value in raw_weights if value.strip()]
        loss = float(Decimal(loss_weight))
        if not weights:
            raise ValueError("Enter at least one child weight.")
    except (InvalidOperation, ValueError, OverflowError):
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Enter valid child weights and loss weight.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        LotService(db).split_lot(
            lot_id,
            weights,
            loss,
            loss_reason or None,
            actor_id=current_user.id,
        )
    except HTTPException as exc:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error=str(exc.detail),
            form_data=form_data,
            status_code=exc.status_code,
        )
    return RedirectResponse(url=f"/lots/{lot_id}?success=split", status_code=303)


@app.post(
    "/lots/{lot_id}/processing",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def record_processing_step(
    lot_id: UUID,
    request: Request,
    step_type: str = Form(...),
    weight_in: str = Form(...),
    weight_out: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Record a supported processing operation and calculate its yield."""
    if current_user.role != "Processor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Processor role required",
        )
    form_data = {
        "step_type": step_type,
        "weight_in": weight_in,
        "weight_out": weight_out,
    }
    if step_type not in {"Gutting", "Filleting", "Freezing", "Packing"}:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Choose a valid processing step.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        input_weight = Decimal(weight_in)
        output_weight = Decimal(weight_out)
        if (
            not input_weight.is_finite()
            or not output_weight.is_finite()
            or input_weight <= 0
            or output_weight < 0
            or input_weight >= Decimal("100000000")
            or output_weight >= Decimal("100000000")
            or input_weight.quantize(Decimal("0.01")) != input_weight
            or output_weight.quantize(Decimal("0.01")) != output_weight
        ):
            raise ValueError
        if output_weight > input_weight:
            raise ValueError("Weight out cannot exceed weight in.")
    except (InvalidOperation, ValueError):
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Enter valid weights; weight out cannot exceed weight in.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    yield_pct = (output_weight / input_weight * Decimal("100")).quantize(
        Decimal("0.01")
    )
    with db.begin():
        if db.get(Lot, lot_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lot not found",
            )
        db.add(
            ProcessingStep(
                lot_id=lot_id,
                step_type=step_type,
                operator_id=current_user.id,
                weight_in=input_weight,
                weight_out=output_weight,
                yield_pct=yield_pct,
            )
        )

    warning = (
        "&warning=low-yield"
        if step_type == "Filleting" and yield_pct < Decimal("40")
        else ""
    )
    return RedirectResponse(
        url=f"/lots/{lot_id}?success=processing{warning}",
        status_code=303,
    )


@app.post(
    "/lots/{lot_id}/temperatures",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def log_temperature_from_form(
    lot_id: UUID,
    request: Request,
    temp_celsius: str = Form(...),
    temperature_type: str = Form(...),
    location: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Record a temperature observation for a lot."""
    form_data = {
        "temp_celsius": temp_celsius,
        "temperature_type": temperature_type,
        "location": location,
    }
    if temperature_type not in {"Chilled", "Frozen"}:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Choose Chilled or Frozen storage.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        temperature = Decimal(temp_celsius)
        if (
            not temperature.is_finite()
            or temperature < Decimal("-999.99")
            or temperature > Decimal("999.99")
            or temperature.quantize(Decimal("0.01")) != temperature
        ):
            raise ValueError("Temperature must be within -999.99 to 999.99 with two decimals.")
    except (InvalidOperation, ValueError):
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Enter a valid temperature with no more than two decimal places.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    cleaned_location = location.strip()
    if not cleaned_location:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Location is required.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    with db.begin():
        if db.get(Lot, lot_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lot not found",
            )
        db.add(
            TemperatureLog(
                lot_id=lot_id,
                temp_celsius=temperature,
                temperature_type=temperature_type,
                location=cleaned_location,
                is_breach=(
                    temperature > Decimal("4")
                    if temperature_type == "Chilled"
                    else temperature > Decimal("-18")
                ),
            )
        )
    return RedirectResponse(url=f"/lots/{lot_id}?success=temperature", status_code=303)


@app.post(
    "/lots/{lot_id}/inspections",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def inspect_lot_from_form(
    lot_id: UUID,
    request: Request,
    result: str = Form(...),
    grade: str = Form(...),
    inspector_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Save an inspection result for a lot."""
    if current_user.role != "Inspector":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inspector role required",
        )
    form_data = {
        "result": result,
        "grade": grade,
        "inspector_id": inspector_id,
    }
    if result not in {"pass", "fail"} or grade not in {"A", "B", "C"}:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Choose a valid inspection result and grade.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        selected_inspector_id = UUID(inspector_id)
    except ValueError:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error="Select an inspector from the list.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    validation_error = None
    inspected_at = datetime.now(timezone.utc)
    with db.begin():
        lot = db.get(Lot, lot_id)
        inspector = db.get(User, selected_inspector_id)
        if lot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lot not found",
            )
        if inspector is None or inspector.role != "Inspector":
            validation_error = "Select an authorized inspector from the list."
        else:
            latest_breach_at = db.scalar(
                select(func.max(TemperatureLog.recorded_at)).where(
                    TemperatureLog.lot_id == lot_id,
                    TemperatureLog.is_breach.is_(True),
                )
            )
            if (
                result == "pass"
                and latest_breach_at is not None
                and inspected_at
                <= (
                    latest_breach_at.replace(tzinfo=timezone.utc)
                    if latest_breach_at.tzinfo is None
                    else latest_breach_at
                )
            ):
                validation_error = (
                    "A passing inspection must be recorded after the latest "
                    "temperature breach."
                )
            else:
                db.add(
                    Inspection(
                        lot_id=lot_id,
                        inspector_id=inspector.id,
                        grade=grade,
                        passed=result == "pass",
                        inspected_at=inspected_at,
                    )
                )
                if result == "pass" and lot.catch_id is not None:
                    catch = db.get(Catch, lot.catch_id)
                    vessel = (
                        db.get(Vessel, catch.vessel_id)
                        if catch is not None
                        else None
                    )
                    if vessel is not None and vessel.owner_phone:
                        MockSMSAdapter(db).send_sms(
                            recipient=vessel.owner_phone,
                            message=f"Lot inspection passed: {lot.lot_code}.",
                        )
    if validation_error is not None:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            current_user,
            error=validation_error,
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url=f"/lots/{lot_id}?success=inspection", status_code=303)


@app.get(
    "/lots/{lot_id}/label",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def lot_label_page(
    lot_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    _authenticated: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render a printable QR label for a lot's public trace endpoint."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found",
        )
    trace_url = (
        f"{PUBLIC_TRACE_BASE_URL.rstrip('/')}/{quote(lot.lot_code, safe='')}"
    )
    return templates.TemplateResponse(
        request=request,
        name="print_label.html",
        context={
            "language": _selected_language(request),
            "t": get_translations(_selected_language(request)),
            "active_page": "lots",
            "lot": lot,
            "trace_url": trace_url,
            "qr_url": f"/lots/{lot.id}/label/qr.png",
        },
    )


@app.get(
    "/lots/{lot_id}/label/qr.png",
    response_class=Response,
    include_in_schema=False,
)
def lot_label_qr(
    lot_id: UUID,
    db: Session = Depends(get_db),
    _authenticated: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Return a PNG QR code that opens the lot's public trace endpoint."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found",
        )
    trace_url = (
        f"{PUBLIC_TRACE_BASE_URL.rstrip('/')}/{quote(lot.lot_code, safe='')}"
    )
    qr_image = qrcode.make(trace_url)
    output = BytesIO()
    qr_image.save(output, format="PNG")
    return Response(content=output.getvalue(), media_type="image/png")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    language = _selected_language(request)
    translations = get_translations(language)
    dashboard = DashboardService(db).get_dashboard_data()
    response = templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "dashboard",
            "current_user": current_user,
            "today_label": translations["operations_overview"],
            "total_catch": f"{dashboard.total_catch_kg:,.2f}",
            "active_consignments": dashboard.active_consignments,
            "temperature_alerts": dashboard.temp_alerts,
            "species_labels": dashboard.species_labels,
            "species_weights": dashboard.species_weights,
            "landing_site_labels": dashboard.landing_site_labels,
            "landing_site_weights": dashboard.landing_site_weights,
            "recent_lots": [
                {
                    **lot,
                    "status": translations.get(
                        f"lot_status_{lot['status'].lower()}", lot["status"]
                    ),
                }
                for lot in dashboard.recent_lots
            ],
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/lots",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def lots_page(
    request: Request,
    q: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the searchable lot inventory for authenticated staff."""
    language = _selected_language(request)
    translations = get_translations(language)
    search_term = q.strip()
    statement = (
        select(Lot, Species.name)
        .join(Species, Species.id == Lot.species_id)
        .order_by(Lot.lot_code.desc())
    )
    if search_term:
        pattern = f"%{search_term}%"
        statement = statement.where(
            or_(Lot.lot_code.ilike(pattern), Species.name.ilike(pattern))
        )

    rows = [
        {
            "lot_id": lot.lot_code,
            "species": species_name,
            "weight": f"{lot.current_weight:,.2f} kg",
            "status": translations.get(
                f"lot_status_{lot.status.lower()}", lot.status
            ),
            "trace_url": f"/trace?lot_code={quote(lot.lot_code, safe='')}",
            "detail_url": f"/lots/{lot.id}",
        }
        for lot, species_name in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="lots.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "lots",
            "current_user": current_user,
            "query": search_term,
            "lots": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/vessels",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def vessels_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the vessel registry for authenticated staff."""
    return _render_vessels(request, db, current_user)


@app.post(
    "/vessels/form",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def create_vessel_from_form(
    request: Request,
    name: str = Form(...),
    reg_number: str = Form(...),
    license_number: str = Form(...),
    license_expiry: str = Form(...),
    owner_name: str = Form(...),
    home_port: str = Form(...),
    gear_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    form_data = {
        "name": name,
        "reg_number": reg_number,
        "license_number": license_number,
        "license_expiry": license_expiry,
        "owner_name": owner_name,
        "home_port": home_port,
        "gear_type": gear_type,
    }
    try:
        vessel_data = VesselCreate.model_validate(
            {
                key: value.strip()
                for key, value in form_data.items()
            }
        )
    except ValidationError:
        return _render_vessels(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "vessel_form_error"
            ],
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        VesselService(db).create_vessel(vessel_data, current_user.id)
    except IntegrityError:
        return _render_vessels(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "vessel_numbers_unique"
            ],
            form_data=form_data,
            status_code=status.HTTP_409_CONFLICT,
        )
    return RedirectResponse(
        url="/vessels?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get(
    "/consignments/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def create_consignment_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the exporter form with currently eligible lots."""
    if current_user.role not in {"Admin", "Exporter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Exporter role required",
        )
    return _render_consignment_form(request, db)


@app.post(
    "/consignments",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def create_consignment_from_form(
    request: Request,
    buyer_name: str = Form(...),
    destination_country: str = Form(...),
    shipping_date: str = Form(...),
    container_number: str = Form(...),
    lot_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Create a consignment from selected eligible lots."""
    if current_user.role not in {"Admin", "Exporter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Exporter role required",
        )
    form_data: dict[str, object] = {
        "buyer_name": buyer_name,
        "destination_country": destination_country,
        "shipping_date": shipping_date,
        "container_number": container_number,
        "lot_ids": lot_ids,
    }
    try:
        selected_lot_ids = [UUID(value) for value in lot_ids]
        selected_shipping_date = date.fromisoformat(shipping_date)
    except ValueError:
        return _render_consignment_form(
            request,
            db,
            form_data=form_data,
            error="Enter a valid shipping date and select eligible lots.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    buyer = buyer_name.strip()
    destination = destination_country.strip()
    container = container_number.strip()
    if not buyer or not destination or not container:
        return _render_consignment_form(
            request,
            db,
            form_data=form_data,
            error="Buyer, destination, and container number are required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        consignment_id = ConsignmentService(db).create_consignment(
            lot_ids=selected_lot_ids,
            buyer_name=buyer,
            destination_country=destination,
            shipping_date=selected_shipping_date,
            container_number=container,
            actor_id=current_user.id,
        )
    except HTTPException as exc:
        return _render_consignment_form(
            request,
            db,
            form_data=form_data,
            error=str(exc.detail),
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url=f"/consignments?success={consignment_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get(
    "/consignments",
    response_class=HTMLResponse,
    dependencies=[Depends(require_html_user)],
    include_in_schema=False,
)
def consignments_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render consignment records and their lot counts for authenticated staff."""
    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(
            Consignment,
            func.count(ConsignmentLot.lot_id).label("lot_count"),
        )
        .outerjoin(
            ConsignmentLot,
            ConsignmentLot.consignment_id == Consignment.id,
        )
        .group_by(Consignment.id)
        .order_by(Consignment.shipping_date.desc(), Consignment.id)
    )
    rows = [
        {
            "id": consignment.id,
            "buyer": consignment.buyer_name,
            "destination": consignment.destination_country,
            "shipping_date": consignment.shipping_date.isoformat(),
            "container": consignment.container_number,
            "lot_count": lot_count,
            "status": translations.get(
                f"lot_status_{consignment.status.lower()}",
                consignment.status,
            ),
            "certificate_url": (
                f"/consignments/{consignment.id}/certificate.pdf"
            ),
        }
        for consignment, lot_count in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="consignments.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "consignments",
            "current_user": current_user,
            "consignments": rows,
            "can_manage_exports": getattr(current_user, "role", None)
            in {"Admin", "Exporter"},
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get("/trace", response_class=HTMLResponse, include_in_schema=False)
def public_trace_page(
    request: Request,
    lot_code: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the public lot lookup and traceability journey."""
    language = _selected_language(request)
    translations = get_translations(language)
    search_code = lot_code.strip() if lot_code is not None else ""
    trace = None
    not_found = False
    response_status = status.HTTP_200_OK

    if search_code:
        try:
            trace = TraceabilityService(db).get_trace(search_code)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            not_found = True
            response_status = status.HTTP_404_NOT_FOUND

    response = templates.TemplateResponse(
        request=request,
        name="trace.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "trace",
            "lot_code": search_code,
            "trace": trace,
            "not_found": not_found,
            "response_status": response_status,
        },
        status_code=response_status,
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/landing-sites",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def landing_sites_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render landing sites for authenticated users."""
    return _render_landing_sites(request, db, current_user)


@app.post(
    "/landing-sites",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
def create_landing_site(
    request: Request,
    name: str = Form(..., max_length=255),
    region: str = Form(..., max_length=255),
    gps_lat: str = Form(default="", max_length=32),
    gps_lng: str = Form(default="", max_length=32),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse | RedirectResponse:
    """Create a landing site after validating its name, region, and coordinates."""
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    form_data = {
        "name": name,
        "region": region,
        "gps_lat": gps_lat,
        "gps_lng": gps_lng,
    }
    clean_name = name.strip()
    clean_region = region.strip()
    if not clean_name or not clean_region:
        return _render_landing_sites(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "landing_site_form_error"
            ],
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if bool(gps_lat.strip()) != bool(gps_lng.strip()):
        return _render_landing_sites(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "landing_site_form_error"
            ],
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    coordinates: list[Decimal | None] = []
    try:
        for raw_value, minimum, maximum, field_name in (
            (gps_lat, Decimal("-90"), Decimal("90"), "Latitude"),
            (gps_lng, Decimal("-180"), Decimal("180"), "Longitude"),
        ):
            value = raw_value.strip()
            if not value:
                coordinates.append(None)
                continue
            coordinate = Decimal(value)
            if (
                not coordinate.is_finite()
                or coordinate < minimum
                or coordinate > maximum
                or coordinate.quantize(Decimal("0.000001")) != coordinate
            ):
                raise ValueError(f"{field_name} must be a valid GPS coordinate.")
            coordinates.append(coordinate)
    except (InvalidOperation, ValueError):
        return _render_landing_sites(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "landing_site_form_error"
            ],
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with db.begin():
            db.add(
                LandingSite(
                    name=clean_name,
                    region=clean_region,
                    gps_lat=coordinates[0],
                    gps_lng=coordinates[1],
                    is_active=True,
                )
            )
    except IntegrityError:
        return _render_landing_sites(
            request,
            db,
            current_user,
            error=get_translations(_selected_language(request))[
                "landing_site_name_exists"
            ],
            form_data=form_data,
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse(
        url="/landing-sites?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get(
    "/users",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the account and assigned-site directory for administrators."""
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(User.email, User.role, LandingSite.name)
        .outerjoin(LandingSite, LandingSite.id == User.assigned_site_id)
        .order_by(User.email)
    )
    rows = [
        {
            "email": email,
            "role": role,
            "site": site_name or translations["unassigned"],
        }
        for email, role, site_name in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "users",
            "current_user": current_user,
            "users": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/processing",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def processing_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render processing records for the sidebar destination."""
    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(ProcessingStep, Lot.lot_code, User.email)
        .join(Lot, Lot.id == ProcessingStep.lot_id)
        .outerjoin(User, User.id == ProcessingStep.operator_id)
        .order_by(ProcessingStep.id.desc())
    )
    rows = [
        {
            "lot": lot_code,
            "step": step.step_type,
            "operator": email or translations["unassigned"],
            "weight_in": f"{step.weight_in:,.2f} kg",
            "weight_out": f"{step.weight_out:,.2f} kg",
            "yield": f"{step.yield_pct}%" if step.yield_pct is not None else "—",
        }
        for step, lot_code, email in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="activity_list.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "processing",
            "current_user": current_user,
            "page_title": translations["processing"],
            "page_description": translations["processing_page_description"],
            "caption": translations["processing_caption"],
            "empty_message": translations["no_processing"],
            "columns": [
                {"key": "lot", "label": translations["lot_id"]},
                {"key": "step", "label": translations["processing_step"]},
                {"key": "operator", "label": translations["operator"]},
                {"key": "weight_in", "label": translations["weight_in"]},
                {"key": "weight_out", "label": translations["weight_out"]},
                {"key": "yield", "label": translations["yield"]},
            ],
            "rows": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/temperature-logs",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def temperature_logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render recorded cold-chain readings for the sidebar destination."""
    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(TemperatureLog, Lot.lot_code)
        .join(Lot, Lot.id == TemperatureLog.lot_id)
        .order_by(TemperatureLog.recorded_at.desc())
    )
    rows = [
        {
            "lot": lot_code,
            "temperature": f"{log.temp_celsius} °C",
            "temperature_type": log.temperature_type,
            "location": log.location,
            "recorded_at": log.recorded_at.isoformat(),
            "status": (
                translations["temperature_alerts"]
                if log.is_breach
                else translations["within_limits"]
            ),
        }
        for log, lot_code in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="activity_list.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "temperature-logs",
            "current_user": current_user,
            "page_title": translations["temperature_logs"],
            "page_description": translations["temperature_logs_description"],
            "caption": translations["temperature_logs_caption"],
            "empty_message": translations["no_temperature_logs"],
            "columns": [
                {"key": "lot", "label": translations["lot_id"]},
                {"key": "temperature", "label": translations["temperature"]},
                {"key": "temperature_type", "label": "Storage type"},
                {"key": "location", "label": translations["location"]},
                {"key": "recorded_at", "label": translations["recorded_at"]},
                {"key": "status", "label": translations["status"]},
            ],
            "rows": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/inspections",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def inspections_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render quality inspection records for the sidebar destination."""
    language = _selected_language(request)
    translations = get_translations(language)
    statement = (
        select(Inspection, Lot.lot_code, User.email)
        .join(Lot, Lot.id == Inspection.lot_id)
        .join(User, User.id == Inspection.inspector_id)
        .order_by(Inspection.inspected_at.desc())
    )
    rows = [
        {
            "lot": lot_code,
            "inspector": email,
            "grade": inspection.grade,
            "result": (
                translations["passed"]
                if inspection.passed
                else translations["failed"]
            ),
            "inspected_at": inspection.inspected_at.isoformat(),
        }
        for inspection, lot_code, email in db.execute(statement).all()
    ]
    response = templates.TemplateResponse(
        request=request,
        name="activity_list.html",
        context={
            "language": language,
            "t": translations,
            "active_page": "inspections",
            "current_user": current_user,
            "page_title": translations["inspections"],
            "page_description": translations["inspections_description"],
            "caption": translations["inspections_caption"],
            "empty_message": translations["no_inspections"],
            "columns": [
                {"key": "lot", "label": translations["lot_id"]},
                {"key": "inspector", "label": translations["inspector"]},
                {"key": "grade", "label": translations["grade"]},
                {"key": "result", "label": translations["result"]},
                {"key": "inspected_at", "label": translations["inspected_at"]},
            ],
            "rows": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get("/profile", response_class=HTMLResponse, include_in_schema=False)
def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the authenticated user's account details."""
    user = db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "language": language,
            "t": get_translations(language),
            "active_page": "profile",
            "current_user": current_user,
            "page_title": get_translations(language)["my_profile"],
            "user": user,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(
    request: Request,
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render account preferences and language settings."""
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "language": language,
            "t": get_translations(language),
            "active_page": "settings",
            "current_user": current_user,
            "page_title": get_translations(language)["settings"],
            "user": None,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get("/logout", include_in_schema=False)
def logout() -> RedirectResponse:
    """Clear the browser authentication cookie and return to login."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", path="/")
    return response


@app.get("/payments", response_class=HTMLResponse, include_in_schema=False)
def payments_page(
    request: Request,
    receipt: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render the authenticated mock mobile-money payment form and receipt."""
    language = _selected_language(request)
    payment = db.get(PaymentTransaction, receipt) if receipt is not None else None
    if receipt is not None and payment is None:
        raise HTTPException(status_code=404, detail="Payment receipt not found")
    response = templates.TemplateResponse(
        request=request,
        name="payments.html",
        context={
            "language": language,
            "t": get_translations(language),
            "active_page": "payments",
            "current_user": current_user,
            "receipt": payment,
            "error": None,
            "form_data": {},
        },
    )
    _set_language_cookie(response, language)
    return response


@app.post("/payments", response_class=HTMLResponse, include_in_schema=False)
def create_payment(
    request: Request,
    provider: str = Form(...),
    phone_number: str = Form(...),
    amount: str = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> Response:
    """Create a mock mobile-money receipt and queue its SMS atomically."""
    language = _selected_language(request)
    translations = get_translations(language)
    form_data = {
        "provider": provider,
        "phone_number": phone_number,
        "amount": amount,
    }

    payment_providers: dict[str, PaymentProvider] = {
        "EVC Plus": "EVC Plus",
        "Zaad": "Zaad",
    }
    payment_provider = payment_providers.get(provider)
    try:
        parsed_amount = Decimal(amount.strip())
    except InvalidOperation:
        parsed_amount = Decimal("NaN")

    if (
        payment_provider is None
        or not phone_number.strip()
        or len(phone_number.strip()) > 32
        or not parsed_amount.is_finite()
        or parsed_amount <= 0
        or parsed_amount.as_tuple().exponent < -2
        or parsed_amount >= Decimal("10000000000")
    ):
        response = templates.TemplateResponse(
            request=request,
            name="payments.html",
            context={
                "language": language,
                "t": translations,
                "active_page": "payments",
                "current_user": current_user,
                "receipt": None,
                "error": translations["payment_form_error"],
                "form_data": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        _set_language_cookie(response, language)
        return response

    normalized_phone = phone_number.strip()
    reference = f"PAY-{uuid4().hex[:12].upper()}"
    payment_result = MockPaymentAdapter().pay(
        provider=payment_provider,
        amount=parsed_amount,
        currency="USD",
        phone_number=normalized_phone,
        reference=reference,
    )
    payment_id = uuid4()
    with db.begin():
        db.add(
            PaymentTransaction(
                id=payment_id,
                user_id=current_user.id,
                provider=payment_result.provider,
                phone_number=normalized_phone,
                amount=payment_result.amount,
                currency=payment_result.currency,
                reference=payment_result.reference,
                transaction_id=payment_result.transaction_id,
                status="Successful",
            )
        )
        MockSMSAdapter(db).send_sms(
            recipient=normalized_phone,
            message=(
                f"Payment received: {payment_result.amount:.2f} "
                f"{payment_result.currency} via {payment_result.provider}. "
                f"Reference: {payment_result.reference}."
            ),
        )

    return RedirectResponse(
        url=f"/payments?receipt={payment_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/sms-outbox", response_class=HTMLResponse, include_in_schema=False)
def sms_outbox_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthenticatedHTMLUser = Depends(require_html_user),
) -> HTMLResponse:
    """Render queued SMS records for authenticated staff."""
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="sms_outbox.html",
        context={
            "language": language,
            "t": get_translations(language),
            "active_page": "sms-outbox",
            "current_user": current_user,
            "messages": list(
                db.scalars(select(SMSOutbox).order_by(SMSOutbox.created_at.desc()))
            ),
        },
    )
    _set_language_cookie(response, language)
    return response


app.include_router(auth_router)
app.include_router(vessels_router)
app.include_router(lots_router)
app.include_router(traceability_router)
app.include_router(certificates_router)
