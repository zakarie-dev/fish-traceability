from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, get_jwt_secret_key
from app.main import app
from app.models import (
    Base,
    Catch,
    Inspection,
    LandingSite,
    Lot,
    Species,
    TemperatureLog,
    User,
    Vessel,
)


@pytest.fixture
def client_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    site_id, species_id, officer_id, inspector_id, vessel_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with test_session.begin() as db:
        db.add_all(
            [
                LandingSite(id=site_id, name="Berbera"),
                Species(id=species_id, name="Tuna", is_protected=False),
                User(
                    id=officer_id,
                    email="officer@test.local",
                    hashed_password="unused",
                    role="Officer",
                ),
                User(
                    id=inspector_id,
                    email="inspector@test.local",
                    hashed_password="unused",
                    role="Inspector",
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
                "inspector_id": inspector_id,
                "vessel_id": vessel_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
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

    temperature = client.post(
        f"/lots/{lot_id}/temperatures",
        data={"temp_celsius": "-2.50", "location": "Cold store"},
        follow_redirects=False,
    )
    assert temperature.status_code == 303

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
