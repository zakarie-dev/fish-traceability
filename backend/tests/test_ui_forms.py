from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, get_jwt_secret_key
from app.dependencies import require_html_user
from app.main import app
from app.models import (
    Base,
    AuditLog,
    Catch,
    Consignment,
    ConsignmentLot,
    Inspection,
    LandingSite,
    Lot,
    LotLink,
    PaymentTransaction,
    ProcessingStep,
    Species,
    SMSOutbox,
    TemperatureLog,
    User,
    Vessel,
)
from app.schemas import VesselCreate
from app.services.vessel_service import VesselService


@pytest.fixture
def client_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    (
        site_id,
        species_id,
        officer_id,
        processor_id,
        inspector_id,
        vessel_id,
        exporter_id,
    ) = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with test_session.begin() as db:
        db.add_all(
            [
                LandingSite(id=site_id, name="Berbera", region="Woqooyi Galbeed"),
                Species(id=species_id, name="Tuna", is_protected=False),
                User(
                    id=officer_id,
                    email="officer@test.local",
                    hashed_password="unused",
                    role="Officer",
                ),
                User(
                    id=processor_id,
                    email="processor@test.local",
                    hashed_password="unused",
                    role="Processor",
                ),
                User(
                    id=inspector_id,
                    email="inspector@test.local",
                    hashed_password="unused",
                    role="Inspector",
                ),
                User(
                    id=exporter_id,
                    email="exporter@test.local",
                    hashed_password="unused",
                    role="Exporter",
                ),
                Vessel(
                    id=vessel_id,
                    name="Al-Baraka",
                    reg_number="REG-1",
                    license_number="LIC-1",
                    license_expiry=date(2030, 1, 1),
                    owner_name="Owner",
                    home_port="Berbera",
                    gear_type="Longline",
                ),
            ]
        )

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = jwt.encode(
            {
                "sub": str(officer_id),
                "role": "Officer",
                "exp": datetime.now(timezone.utc)
                + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            },
            get_jwt_secret_key(),
            algorithm=JWT_ALGORITHM,
        )
        client = TestClient(app)
        client.cookies.set("access_token", token)
        yield (
            client,
            test_session,
            {
                "site_id": site_id,
                "species_id": species_id,
                "officer_id": officer_id,
                "processor_id": processor_id,
                "inspector_id": inspector_id,
                "vessel_id": vessel_id,
                "exporter_id": exporter_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_html_user, None)
        engine.dispose()


def test_html_authentication_redirects_or_accepts_valid_credentials(
    client_and_session,
):
    client, _, ids = client_and_session

    client.cookies.clear()
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    response = client.get(f"/lots/{uuid4()}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    response = client.post(
        "/catches",
        data={
            "vessel_id": str(ids["vessel_id"]),
            "species_id": str(ids["species_id"]),
            "weight": "20.00",
            "catch_area": "Berbera offshore",
            "catch_date": "2026-11-01",
            "landing_date": "2026-11-02",
            "landing_site_id": str(ids["site_id"]),
            "officer_id": str(ids["officer_id"]),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    client.cookies.set("access_token", "invalid-token")
    response = client.get("/catches", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    client.cookies.clear()
    token = jwt.encode(
        {
            "sub": str(ids["officer_id"]),
            "role": "Officer",
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        get_jwt_secret_key(),
        algorithm=JWT_ALGORITHM,
    )
    response = client.get(
        "/catches",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_login_supports_html_cookie_and_json_api(client_and_session, monkeypatch):
    from app.schemas import TokenResponse
    from app.services.auth_service import AuthService

    client, _, _ = client_and_session
    client.cookies.clear()
    direct_route = client.get("/auth/login", follow_redirects=False)
    assert direct_route.status_code == 303
    assert direct_route.headers["location"] == "/login"

    login_page = client.get("/login")
    assert '<form method="POST" action="/auth/login"' in login_page.text

    monkeypatch.setattr(
        AuthService,
        "authenticate",
        lambda self, email, password: TokenResponse(access_token="signed-token"),
    )

    form_response = client.post(
        "/auth/login",
        data={"email": "officer@test.local", "password": "demo-password"},
        follow_redirects=False,
    )
    assert form_response.status_code == 303
    assert form_response.headers["location"] == "/dashboard"
    cookie = form_response.headers["set-cookie"]
    assert "access_token=signed-token" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()

    api_response = client.post(
        "/auth/login",
        json={"email": "officer@test.local", "password": "demo-password"},
    )
    assert api_response.status_code == 200
    assert api_response.json() == {
        "access_token": "signed-token",
        "token_type": "bearer",
    }
    assert "set-cookie" not in api_response.headers


def test_catch_and_lot_forms_write_records_transactionally(client_and_session):
    client, test_session, ids = client_and_session
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    catch_page = client.get("/catches")
    assert catch_page.status_code == 200
    assert 'action="/catches"' in catch_page.text

    response = client.post(
        "/catches",
        data={
            "vessel_id": str(ids["vessel_id"]),
            "species_id": str(ids["species_id"]),
            "weight": "20.00",
            "catch_area": "Berbera offshore",
            "catch_date": "2026-11-01",
            "landing_date": "2026-11-02",
            "landing_site_id": str(ids["site_id"]),
            "officer_id": str(ids["officer_id"]),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/catches?success=catch"

    with test_session() as db:
        catch = db.scalar(select(Catch))
        lot = db.scalar(select(Lot))
        assert catch is not None
        assert lot is not None
        assert catch.gear_used == "Longline"
        assert lot.current_weight == Decimal("20.00")
        lot_id = lot.id

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Record a catch" in dashboard.text
    assert f"/lots/{lot_id}" in dashboard.text

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["processor_id"],
        role="Processor",
    )
    invalid_split = client.post(
        f"/lots/{lot_id}/split",
        data={
            "child_weights": "18.00",
            "loss_weight": "2.00",
            "loss_reason": "",
        },
    )
    assert invalid_split.status_code == 400
    assert "loss reason is required" in invalid_split.text.lower()
    with test_session() as db:
        assert db.get(Lot, lot_id).status == "Available"

    split = client.post(
        f"/lots/{lot_id}/split",
        data={
            "child_weights": "18.00",
            "loss_weight": "2.00",
            "loss_reason": "Handling loss",
        },
        follow_redirects=False,
    )
    assert split.status_code == 303
    with test_session() as db:
        assert db.get(Lot, lot_id).status == "Split"
        assert db.scalar(select(func.count(Lot.id))) == 2
        split_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "lot.split",
                AuditLog.entity_id == lot_id,
            )
        )
        assert split_audit is not None
        assert split_audit.user_id == ids["processor_id"]

    temperature = client.post(
        f"/lots/{lot_id}/temperatures",
        data={
            "temp_celsius": "-2.50",
            "temperature_type": "Chilled",
            "location": "Cold store",
        },
        follow_redirects=False,
    )
    assert temperature.status_code == 303

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["inspector_id"],
        role="Inspector",
    )
    inspection = client.post(
        f"/lots/{lot_id}/inspections",
        data={
            "result": "pass",
            "grade": "A",
            "inspector_id": str(ids["inspector_id"]),
        },
        follow_redirects=False,
    )
    assert inspection.status_code == 303

    with test_session() as db:
        assert db.scalar(select(func.count(TemperatureLog.id))) == 1
        assert db.scalar(select(func.count(Inspection.id))) == 1

    detail_page = client.get(f"/lots/{lot_id}")
    assert detail_page.status_code == 200
    assert 'action="/lots/' in detail_page.text
    assert "Cold store" in detail_page.text
    assert "Pass" in detail_page.text


def test_role_gated_forms_are_hidden_and_write_routes_are_protected(
    client_and_session,
):
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, test_session, ids = client_and_session
    with test_session.begin() as db:
        lot = Lot(
            lot_code="LOT-ROLE-1",
            catch_id=None,
            species_id=ids["species_id"],
            current_weight=Decimal("10.00"),
            status="Available",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id

    def set_role(role, user_id):
        app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
            id=user_id,
            role=role,
        )

    set_role("Officer", ids["officer_id"])
    officer_detail = client.get(f"/lots/{lot_id}")
    assert officer_detail.status_code == 200
    assert "Log temperature" in officer_detail.text
    assert "Split lot" not in officer_detail.text
    assert "Record processing step" not in officer_detail.text
    assert "Inspect lot" not in officer_detail.text
    assert client.get("/catches").status_code == 200

    assert client.post(
        f"/lots/{lot_id}/split",
        data={"child_weights": "10", "loss_weight": "0"},
    ).status_code == 403
    assert client.post(
        f"/lots/{lot_id}/processing",
        data={"step_type": "Filleting", "weight_in": "10", "weight_out": "9"},
    ).status_code == 403
    assert client.post(
        f"/lots/{lot_id}/inspections",
        data={
            "result": "pass",
            "grade": "A",
            "inspector_id": str(ids["inspector_id"]),
        },
    ).status_code == 403

    set_role("Admin", ids["officer_id"])
    assert client.get("/catches").status_code == 403
    assert client.post(
        "/catches",
        data={
            "vessel_id": str(ids["vessel_id"]),
            "species_id": str(ids["species_id"]),
            "weight": "10",
            "catch_area": "Berbera offshore",
            "catch_date": "2026-11-01",
            "landing_date": "2026-11-02",
            "landing_site_id": str(ids["site_id"]),
            "officer_id": str(ids["officer_id"]),
        },
    ).status_code == 403
    assert "Recall Lot" in client.get(f"/lots/{lot_id}").text

    set_role("Officer", ids["officer_id"])
    assert client.post(
        "/vessels/form",
        data={
            "name": "Unauthorized vessel",
            "reg_number": "TEST-UNAUTHORIZED",
            "license_number": "TEST-UNAUTHORIZED-LIC",
            "license_expiry": "2030-12-31",
            "owner_name": "Test Owner",
            "home_port": "Berbera",
            "gear_type": "Longline",
        },
    ).status_code == 403

    set_role("Processor", ids["processor_id"])
    processor_detail = client.get(f"/lots/{lot_id}")
    assert "Split lot" in processor_detail.text
    assert "Record processing step" in processor_detail.text
    assert "Inspect lot" not in processor_detail.text

    set_role("Inspector", ids["inspector_id"])
    inspector_detail = client.get(f"/lots/{lot_id}")
    assert "Inspect lot" in inspector_detail.text
    assert "Split lot" not in inspector_detail.text
    assert "Record processing step" not in inspector_detail.text
    assert "Recall Lot" in inspector_detail.text


def test_temperature_breach_thresholds_depend_on_storage_type(client_and_session):
    client, test_session, ids = client_and_session
    with test_session.begin() as db:
        lot = Lot(
            lot_code="LOT-TEMP-THRESHOLD",
            catch_id=None,
            species_id=ids["species_id"],
            current_weight=Decimal("10.00"),
            status="Available",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id

    readings = (
        ("4.00", "Chilled", False),
        ("4.01", "Chilled", True),
        ("-18.00", "Frozen", False),
        ("-17.99", "Frozen", True),
    )
    for temperature, temperature_type, _expected_breach in readings:
        response = client.post(
            f"/lots/{lot_id}/temperatures",
            data={
                "temp_celsius": temperature,
                "temperature_type": temperature_type,
                "location": "Test cold store",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    with test_session() as db:
        saved = {
            (str(log.temp_celsius), log.temperature_type): log.is_breach
            for log in db.scalars(
                select(TemperatureLog).where(TemperatureLog.lot_id == lot_id)
            )
        }
    assert saved == {
        (temperature, temperature_type): expected_breach
        for temperature, temperature_type, expected_breach in readings
    }


def test_admin_can_create_vessel_from_browser_form(client_and_session):
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, test_session, ids = client_and_session
    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["officer_id"],
        role="Admin",
    )
    response = client.post(
        "/vessels/form",
        data={
            "name": "Daryeel Test",
            "reg_number": "TEST-REG-200",
            "license_number": "TEST-LIC-200",
            "license_expiry": "2030-12-31",
            "owner_name": "Test Owner",
            "home_port": "Berbera",
            "gear_type": "Longline",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/vessels?created=1"
    with test_session() as db:
        vessel = db.scalar(
            select(Vessel).where(Vessel.reg_number == "TEST-REG-200")
        )
        assert vessel is not None
        assert vessel.license_number == "TEST-LIC-200"
        assert vessel.owner_name == "Test Owner"
        assert vessel.home_port == "Berbera"
        assert vessel.gear_type == "Longline"
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "vessel.create",
                AuditLog.entity_id == vessel.id,
            )
        )
        assert audit is not None


def test_processing_step_validates_weights_and_warns_for_low_filleting_yield(
    client_and_session,
):
    client, test_session, ids = client_and_session
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["processor_id"],
        role="Processor",
    )
    with test_session.begin() as db:
        lot = Lot(
            lot_code="LOT-PROCESS-1",
            catch_id=None,
            species_id=ids["species_id"],
            current_weight=Decimal("10.00"),
            status="Available",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id

    invalid = client.post(
        f"/lots/{lot_id}/processing",
        data={"step_type": "Filleting", "weight_in": "10", "weight_out": "10.01"},
    )
    assert invalid.status_code == 400
    assert "cannot exceed" in invalid.text

    recorded = client.post(
        f"/lots/{lot_id}/processing",
        data={"step_type": "Filleting", "weight_in": "10", "weight_out": "3.99"},
        follow_redirects=False,
    )
    assert recorded.status_code == 303
    assert "warning=low-yield" in recorded.headers["location"]
    low_yield_page = client.get(recorded.headers["location"])
    assert "filleting yield is below 40%" in low_yield_page.text.lower()

    standard_yield = client.post(
        f"/lots/{lot_id}/processing",
        data={"step_type": "Filleting", "weight_in": "10", "weight_out": "4"},
        follow_redirects=False,
    )
    assert standard_yield.status_code == 303
    assert "warning=" not in standard_yield.headers["location"]

    with test_session() as db:
        step = db.scalar(select(ProcessingStep).where(ProcessingStep.lot_id == lot_id))
        assert step is not None
        assert step.yield_pct == Decimal("39.90")


def test_breach_requires_a_later_pass_before_export_and_creates_consignment(
    client_and_session,
):
    client, test_session, ids = client_and_session
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["exporter_id"],
        role="Exporter",
    )
    try:
        breach_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        with test_session.begin() as db:
            lot = Lot(
                lot_code="LOT-BREACH-1",
                catch_id=None,
                species_id=ids["species_id"],
                current_weight=Decimal("10.00"),
                status="Available",
            )
            db.add(lot)
            db.flush()
            lot_id = lot.id
            db.add_all(
                [
                    TemperatureLog(
                        lot_id=lot_id,
                        temp_celsius=Decimal("5.00"),
                        temperature_type="Chilled",
                        location="Cold store",
                        is_breach=True,
                        recorded_at=breach_time,
                    ),
                    Inspection(
                        lot_id=lot_id,
                        inspector_id=ids["inspector_id"],
                        grade="A",
                        passed=True,
                        inspected_at=breach_time - timedelta(minutes=1),
                    ),
                ]
            )

        page = client.get("/consignments/new")
        assert page.status_code == 200
        assert "LOT-BREACH-1" not in page.text
        detail = client.get(f"/lots/{lot_id}")
        assert "open temperature breach" in detail.text.lower()

        form_data = {
            "buyer_name": "Buyer",
            "destination_country": "Somalia",
            "shipping_date": "2026-11-20",
            "container_number": "CONT-100",
            "lot_ids": str(lot_id),
        }
        rejected = client.post("/consignments", data=form_data)
        assert rejected.status_code == 400

        app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
            id=ids["inspector_id"],
            role="Inspector",
        )
        inspected = client.post(
            f"/lots/{lot_id}/inspections",
            data={
                "result": "pass",
                "grade": "A",
                "inspector_id": str(ids["inspector_id"]),
            },
            follow_redirects=False,
        )
        assert inspected.status_code == 303

        app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
            id=ids["exporter_id"],
            role="Exporter",
        )
        page = client.get("/consignments/new")
        assert "LOT-BREACH-1" in page.text
        created = client.post(
            "/consignments",
            data=form_data,
            follow_redirects=False,
        )
        assert created.status_code == 303
        assert created.headers["location"].startswith("/consignments?success=")
        consignment_page = client.get("/consignments")
        assert "/certificate.pdf" in consignment_page.text

        with test_session() as db:
            consignment = db.scalar(select(Consignment))
            assert consignment is not None
            assert db.scalar(
                select(ConsignmentLot).where(
                    ConsignmentLot.consignment_id == consignment.id,
                    ConsignmentLot.lot_id == lot_id,
                )
            ) is not None
            assert db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "consignment.create",
                    AuditLog.user_id == ids["exporter_id"],
                )
            ) is not None
    finally:
        app.dependency_overrides.pop(require_html_user, None)


def test_lot_qr_label_uses_configured_public_base_url(
    client_and_session, monkeypatch
):
    client, test_session, ids = client_and_session
    monkeypatch.setattr("app.main.PUBLIC_BASE_URL", "https://trace.example.test")
    with test_session.begin() as db:
        lot = Lot(
            lot_code="LOT-QR-1",
            catch_id=None,
            species_id=ids["species_id"],
            current_weight=Decimal("10.00"),
            status="Available",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id

    page = client.get(f"/lots/{lot_id}/label")
    assert page.status_code == 200
    assert "/lots/" + str(lot_id) + "/label/qr.png" in page.text
    assert "https://trace.example.test/trace/LOT-QR-1" in page.text
    assert "localhost" not in page.text

    image = client.get(f"/lots/{lot_id}/label/qr.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_authenticated_merge_records_audit_event(client_and_session):
    from app.dependencies import get_current_user

    client, test_session, ids = client_and_session
    with test_session.begin() as db:
        lots = [
            Lot(
                lot_code=f"LOT-MERGE-{index}",
                catch_id=None,
                species_id=ids["species_id"],
                current_weight=Decimal("5.00"),
                status="Available",
            )
            for index in (1, 2)
        ]
        db.add_all(lots)
        db.flush()
        lot_ids = [lot.id for lot in lots]

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=ids["officer_id"],
        role="Processor",
    )
    try:
        response = client.post(
            "/lots/merge",
            json={"lot_ids": [str(lot_id) for lot_id in lot_ids]},
        )
        assert response.status_code == 200
        merged_id = UUID(response.json()["merged_lot_id"])
        with test_session() as db:
            merged = db.get(Lot, merged_id)
            assert merged is not None
            assert merged.current_weight == Decimal("10.00")
            audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "lot.merge",
                    AuditLog.entity_id == merged_id,
                )
            )
            assert audit is not None
            assert audit.user_id == ids["officer_id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_processor_can_merge_same_species_lots_from_browser(client_and_session):
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, test_session, ids = client_and_session
    with test_session.begin() as db:
        lots = [
            Lot(
                lot_code=f"LOT-UI-MERGE-{index}",
                catch_id=None,
                species_id=ids["species_id"],
                current_weight=Decimal(weight),
                status="Available",
            )
            for index, weight in ((1, "5.00"), (2, "6.25"))
        ]
        db.add_all(lots)
        db.flush()
        lot_ids = [lot.id for lot in lots]

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["processor_id"],
        role="Processor",
    )
    page = client.get("/lots/merge-selection")
    assert page.status_code == 200
    assert "Merge selected lots · Tuna" in page.text

    response = client.post(
        "/lots/merge-form",
        data={"lot_ids": [str(lot_id) for lot_id in lot_ids]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/lots?merged=1"
    with test_session() as db:
        merged = db.scalar(
            select(Lot).where(Lot.current_weight == Decimal("11.25"))
        )
        assert merged is not None
        assert merged.status == "Available"
        parents = list(db.scalars(select(Lot).where(Lot.id.in_(lot_ids))))
        assert all(parent.status == "Merged" for parent in parents)


def test_inspector_can_recall_from_lot_detail(client_and_session):
    from unittest.mock import patch

    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, _, ids = client_and_session
    lot_id = uuid4()
    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["inspector_id"],
        role="Inspector",
    )
    with patch("app.main.TraceabilityService.recall_lot") as recall:
        response = client.post(
            f"/lots/{lot_id}/recall",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/lots/{lot_id}?success=recall"
    recall.assert_called_once_with(lot_id)


def test_recall_marks_lot_and_consignment_ineligible_for_export(
    client_and_session,
    monkeypatch,
):
    from app.repositories.lot_repository import LotRepository
    from app.services.consignment_service import ConsignmentService
    from app.services.traceability_service import TraceabilityService

    _, test_session, ids = client_and_session
    with test_session.begin() as db:
        lot = Lot(
            lot_code="LOT-RECALL-EXPORT",
            catch_id=None,
            species_id=ids["species_id"],
            current_weight=Decimal("10.00"),
            status="Available",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id
        db.add(
            Inspection(
                lot_id=lot_id,
                inspector_id=ids["inspector_id"],
                grade="A",
                passed=True,
            )
        )

    with test_session() as db:
        assert [lot.id for lot in ConsignmentService(db).get_eligible_lots()] == [
            lot_id
        ]

    with test_session.begin() as db:
        consignment = Consignment(
            buyer_name="Test Buyer",
            destination_country="Somalia",
            shipping_date=date(2026, 11, 20),
            container_number="TEST-RECALL-1",
        )
        db.add(consignment)
        db.flush()
        db.add(ConsignmentLot(consignment_id=consignment.id, lot_id=lot_id))

    monkeypatch.setattr(
        LotRepository,
        "get_descendant_ids",
        lambda _self, _lot_id: [lot_id],
    )
    with test_session() as db:
        TraceabilityService(db).recall_lot(lot_id)

    with test_session() as db:
        recalled_lot = db.get(Lot, lot_id)
        recalled_consignment = db.scalar(select(Consignment))
        assert recalled_lot is not None
        assert recalled_lot.status == "Recalled"
        assert recalled_consignment is not None
        assert recalled_consignment.status == "Recalled"
        assert ConsignmentService(db).get_eligible_lots() == []


def test_mock_payment_persists_receipt_and_queues_sms(client_and_session):
    client, test_session, _ids = client_and_session

    page = client.get("/payments")
    assert page.status_code == 200
    assert "EVC Plus" in page.text
    assert "Zaad" in page.text
    assert "no money is transferred" in page.text

    response = client.post(
        "/payments",
        data={
            "provider": "EVC Plus",
            "phone_number": "+252 63 0000000",
            "amount": "25.50",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/payments?receipt=")

    with test_session() as db:
        payment = db.scalar(select(PaymentTransaction))
        sms = db.scalar(select(SMSOutbox))
        assert payment is not None
        assert payment.provider == "EVC Plus"
        assert payment.phone_number == "+252 63 0000000"
        assert payment.amount == Decimal("25.50")
        assert payment.currency == "USD"
        assert payment.status == "Successful"
        assert payment.transaction_id.startswith("MOCK-")
        assert sms is not None
        assert sms.recipient == payment.phone_number
        assert "Payment received" in sms.message
        assert payment.reference in sms.message

    receipt_page = client.get(response.headers["location"])
    assert receipt_page.status_code == 200
    assert "Payment Successful" in receipt_page.text
    assert "25.50 USD" in receipt_page.text

    outbox_page = client.get("/sms-outbox")
    assert outbox_page.status_code == 200
    assert "Payment received" in outbox_page.text
    assert "+252 63 0000000" in outbox_page.text


def test_mock_payment_rejects_invalid_values_without_saving(
    client_and_session,
):
    client, test_session, _ids = client_and_session
    response = client.post(
        "/payments",
        data={
            "provider": "Invalid provider",
            "phone_number": " ",
            "amount": "-1",
        },
    )

    assert response.status_code == 400
    assert "Choose a provider" in response.text
    with test_session() as db:
        assert db.scalar(select(PaymentTransaction)) is None
        assert db.scalar(select(SMSOutbox)) is None


def test_admin_sidebar_links_to_payments_and_sms_outbox(client_and_session):
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, _, ids = client_and_session
    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["officer_id"],
        role="Admin",
    )

    response = client.get("/payments")

    assert response.status_code == 200
    assert 'href="/payments"' in response.text
    assert 'href="/sms-outbox"' in response.text


def test_passing_inspection_queues_sms_to_vessel_owner(client_and_session):
    from app.dependencies import AuthenticatedHTMLUser, require_html_user

    client, test_session, ids = client_and_session
    lot_id = uuid4()
    with test_session.begin() as db:
        vessel = db.get(Vessel, ids["vessel_id"])
        assert vessel is not None
        vessel.owner_phone = "+252 63 0000000"
        catch = Catch(
            id=uuid4(),
            vessel_id=ids["vessel_id"],
            officer_id=ids["officer_id"],
            landing_site_id=ids["site_id"],
            catch_date=date(2026, 11, 1),
            landing_date=date(2026, 11, 2),
            catch_area="Somali Basin",
            gear_used="Longline",
        )
        db.add(catch)
        db.flush()
        db.add(
            Lot(
                id=lot_id,
                lot_code="LOT-INSPECTION-SMS",
                catch_id=catch.id,
                species_id=ids["species_id"],
                current_weight=Decimal("10.00"),
                status="Available",
            )
        )

    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=ids["inspector_id"],
        role="Inspector",
    )
    response = client.post(
        f"/lots/{lot_id}/inspections",
        data={
            "result": "pass",
            "grade": "A",
            "inspector_id": str(ids["inspector_id"]),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with test_session() as db:
        sms = db.scalar(select(SMSOutbox))
        assert sms is not None
        assert sms.recipient == "+252 63 0000000"
        assert sms.message == "Lot inspection passed: LOT-INSPECTION-SMS."


def test_vessel_creation_records_authenticated_actor(client_and_session):
    _, test_session, ids = client_and_session
    vessel_data = VesselCreate(
        name="Audit Vessel",
        reg_number="REG-AUDIT-1",
        license_number="LIC-AUDIT-1",
        license_expiry=date(2030, 1, 1),
        owner_name="Owner",
        home_port="Berbera",
        gear_type="Longline",
    )
    with test_session() as db:
        vessel = VesselService(db).create_vessel(
            vessel_data,
            actor_id=ids["officer_id"],
        )
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "vessel.create",
                AuditLog.entity_id == vessel.id,
            )
        )
        assert audit is not None
        assert audit.user_id == ids["officer_id"]
