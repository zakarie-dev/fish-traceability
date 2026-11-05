import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import AuthenticatedHTMLUser, require_html_user
from app.main import app


class QueryRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_sidebar_destinations_have_get_routes():
    from pathlib import Path

    base_template = Path(r"C:\fish\templates\base.html").read_text(
        encoding="utf-8"
    )
    destinations = set(
        re.findall(r'href="(/(?:[a-z-]+))"', base_template)
    )
    get_paths = {
        route.path
        for route in app.routes
        if "GET" in getattr(route, "methods", set())
    }

    assert {
        "/dashboard",
        "/landing-sites",
        "/vessels",
        "/catches",
        "/lots",
        "/consignments",
        "/trace",
        "/processing",
        "/temperature-logs",
        "/inspections",
        "/profile",
        "/settings",
        "/logout",
    }.issubset(destinations)
    assert destinations <= get_paths


def test_sidebar_pages_require_authentication(client):
    protected_paths = (
        "/dashboard",
        "/landing-sites",
        "/vessels",
        "/catches",
        "/lots",
        "/consignments",
        "/processing",
        "/temperature-logs",
        "/inspections",
        "/profile",
        "/settings",
    )
    for path in protected_paths:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER, path
        assert response.headers["location"] == "/login", path

    assert client.get("/trace").status_code == status.HTTP_200_OK
    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code == status.HTTP_303_SEE_OTHER
    assert logout_response.headers["location"] == "/login"


def test_landing_sites_admin_can_add_site(authenticated_client):
    db = MagicMock()
    db.scalars.return_value = []
    app.dependency_overrides[get_db] = lambda: db

    response = authenticated_client.post(
        "/landing-sites",
        data={
            "name": "Eyl",
            "region": "Nugaal",
            "gps_lat": "7.980000",
            "gps_lng": "49.820000",
        },
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/landing-sites?created=1"
    created_site = db.add.call_args.args[0]
    assert created_site.name == "Eyl"
    assert created_site.region == "Nugaal"
    assert created_site.gps_lat == Decimal("7.980000")
    assert created_site.gps_lng == Decimal("49.820000")
    assert created_site.is_active is True


def test_landing_sites_reject_invalid_coordinates(authenticated_client):
    db = Mock()
    db.scalars.return_value = []
    app.dependency_overrides[get_db] = lambda: db

    response = authenticated_client.post(
        "/landing-sites",
        data={
            "name": "Eyl",
            "region": "Nugaal",
            "gps_lat": "91",
            "gps_lng": "49.82",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "GPS" in response.text
    db.add.assert_not_called()


def test_landing_sites_show_duplicate_name_error(authenticated_client):
    db = MagicMock()
    db.scalars.return_value = []
    db.add.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    app.dependency_overrides[get_db] = lambda: db

    response = authenticated_client.post(
        "/landing-sites",
        data={"name": "Eyl", "region": "Nugaal"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in response.text


def test_landing_sites_and_users_are_admin_only(client):
    db = MagicMock()
    db.scalars.return_value = []
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_html_user] = lambda: AuthenticatedHTMLUser(
        id=uuid4(),
        role="Officer",
    )

    sites_response = client.get("/landing-sites")
    users_response = client.get("/users")
    create_response = client.post(
        "/landing-sites",
        data={"name": "Eyl", "region": "Nugaal"},
    )

    assert sites_response.status_code == status.HTTP_200_OK
    assert "name=\"name\"" not in sites_response.text
    assert users_response.status_code == status.HTTP_403_FORBIDDEN
    assert create_response.status_code == status.HTTP_403_FORBIDDEN


def test_users_page_lists_roles_and_assigned_sites(authenticated_client):
    db = Mock()
    db.execute.return_value = QueryRows(
        [("officer@example.test", "Officer", "Berbera")]
    )
    app.dependency_overrides[get_db] = lambda: db

    response = authenticated_client.get("/users")

    assert response.status_code == status.HTTP_200_OK
    assert "officer@example.test" in response.text
    assert "Berbera" in response.text
    assert "Officer" in response.text
    assert "hashed_password" not in response.text
    assert 'href="/users" aria-current="page"' in response.text


def test_processing_temperature_inspection_pages_render_rows(authenticated_client):
    processing = SimpleNamespace(
        step_type="Filleting",
        weight_in=Decimal("10.00"),
        weight_out=Decimal("5.00"),
        yield_pct=Decimal("50.00"),
    )
    temperature = SimpleNamespace(
        temp_celsius=Decimal("2.50"),
        location="Berbera cold store",
        recorded_at=date(2026, 11, 5),
        is_breach=False,
    )
    inspection = SimpleNamespace(
        grade="A",
        passed=True,
        inspected_at=date(2026, 11, 5),
    )
    rows = iter(
        [
            QueryRows([(processing, "LOT-1", "processor@example.test")]),
            QueryRows([(temperature, "LOT-1")]),
            QueryRows([(inspection, "LOT-1", "inspector@example.test")]),
        ]
    )
    db = Mock()
    db.execute.side_effect = lambda statement: next(rows)
    app.dependency_overrides[get_db] = lambda: db

    processing_response = authenticated_client.get("/processing")
    temperature_response = authenticated_client.get("/temperature-logs")
    inspections_response = authenticated_client.get("/inspections")

    assert processing_response.status_code == 200
    assert "Filleting" in processing_response.text
    assert "50.00%" in processing_response.text
    assert temperature_response.status_code == 200
    assert "Berbera cold store" in temperature_response.text
    assert inspections_response.status_code == 200
    assert "inspector@example.test" in inspections_response.text
    assert "Passed" in inspections_response.text


def test_profile_settings_pages_render_and_switch_language(authenticated_client):
    profile_user = SimpleNamespace(email="officer@example.test", role="Officer")
    db = Mock()
    db.get.return_value = profile_user
    app.dependency_overrides[get_db] = lambda: db

    profile_response = authenticated_client.get("/profile")
    settings_response = authenticated_client.get("/settings?lang=so")

    assert profile_response.status_code == 200
    assert "officer@example.test" in profile_response.text
    assert "Officer" in profile_response.text
    assert settings_response.status_code == 200
    assert "Doorashada luqadda" in settings_response.text
