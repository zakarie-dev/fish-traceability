from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Form, HTTPException, Query, status
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_html_user
from app.models import (
    Catch,
    Consignment,
    ConsignmentLot,
    Inspection,
    LandingSite,
    Lot,
    Species,
    TemperatureLog,
    User,
    Vessel,
)
from app.routes.auth import router as auth_router
from app.routes.certificates import router as certificates_router
from app.routes.traceability import router as traceability_router
from app.routes.vessels import router as vessels_router
from app.services.dashboard_service import DashboardService
from app.services.lot_service import LotService
from app.services.traceability_service import TraceabilityService
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
    response = templates.TemplateResponse(
        request=request,
        name="catch.html",
        context={
            "language": language,
            "t": get_translations(language),
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
            .order_by(Inspection.id.desc())
        )
    )
    language = _selected_language(request)
    response = templates.TemplateResponse(
        request=request,
        name="lot_detail.html",
        context={
            "language": language,
            "t": get_translations(language),
            "lot": lot,
            "species_name": species.name if species is not None else "Unknown",
            "temperature_logs": temperature_logs,
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
            "form_data": form_data or {},
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
    _authenticated: bool = Depends(require_html_user),
) -> HTMLResponse:
    """Render the browser form used to record a catch and create its initial lot."""
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
    _authenticated: bool = Depends(require_html_user),
) -> Response:
    """Save a catch and corresponding available lot from the HTML form."""
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


@app.get("/lots/{lot_id}", response_class=HTMLResponse, include_in_schema=False)
def lot_detail_page(
    lot_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    _authenticated: bool = Depends(require_html_user),
) -> HTMLResponse:
    """Render lot details and the split, temperature, and inspection forms."""
    return _render_lot_detail(request, db, lot_id)


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
    _authenticated: bool = Depends(require_html_user),
) -> Response:
    """Split a lot using comma- or newline-separated child weights."""
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
            error="Enter valid child weights and loss weight.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        LotService(db).split_lot(lot_id, weights, loss, loss_reason or None)
    except HTTPException as exc:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            error=str(exc.detail),
            form_data=form_data,
            status_code=exc.status_code,
        )
    return RedirectResponse(url=f"/lots/{lot_id}?success=split", status_code=303)


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
    location: str = Form(...),
    db: Session = Depends(get_db),
    _authenticated: bool = Depends(require_html_user),
) -> Response:
    """Record a temperature observation for a lot."""
    form_data = {"temp_celsius": temp_celsius, "location": location}
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
                location=cleaned_location,
                is_breach=False,
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
    _authenticated: bool = Depends(require_html_user),
) -> Response:
    """Save an inspection result for a lot."""
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
            error="Select an inspector from the list.",
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    validation_error = None
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
            db.add(
                Inspection(
                    lot_id=lot_id,
                    inspector_id=inspector.id,
                    grade=grade,
                    passed=result == "pass",
                )
            )
    if validation_error is not None:
        return _render_lot_detail(
            request,
            db,
            lot_id,
            error=validation_error,
            form_data=form_data,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url=f"/lots/{lot_id}?success=inspection", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    _authenticated: bool = Depends(require_html_user),
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
    dependencies=[Depends(require_html_user)],
    include_in_schema=False,
)
def lots_page(
    request: Request,
    q: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
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
            "trace_url": f"/trace/{lot.lot_code}",
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
            "query": search_term,
            "lots": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/vessels",
    response_class=HTMLResponse,
    dependencies=[Depends(require_html_user)],
    include_in_schema=False,
)
def vessels_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the vessel registry for authenticated staff."""
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
            "vessels": rows,
        },
    )
    _set_language_cookie(response, language)
    return response


@app.get(
    "/consignments",
    response_class=HTMLResponse,
    dependencies=[Depends(require_html_user)],
    include_in_schema=False,
)
def consignments_page(
    request: Request,
    db: Session = Depends(get_db),
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
            "buyer": consignment.buyer_name,
            "destination": consignment.destination_country,
            "shipping_date": consignment.shipping_date.isoformat(),
            "container": consignment.container_number,
            "lot_count": lot_count,
            "status": translations.get(
                f"lot_status_{consignment.status.lower()}",
                consignment.status,
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
            "consignments": rows,
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


app.include_router(auth_router)
app.include_router(vessels_router)
app.include_router(traceability_router)
app.include_router(certificates_router)
