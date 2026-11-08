from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException, status
from fastapi.responses import HTMLResponse

from app.database import get_db
from app.main import app


class QueryRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _set_database_override(db):
    app.dependency_overrides[get_db] = lambda: db


def test_authenticated_list_pages_render_database_rows(authenticated_client):
    lot_id = uuid4()
    vessel = SimpleNamespace(
        name="Al-Baraka",
        reg_number="SOM-BRB-1042",
        license_number="LIC-BRB-2026-1042",
        license_expiry=date(2027, 6, 30),
        home_port="Berbera",
        gear_type="Longline",
    )
    consignment = SimpleNamespace(
        id=uuid4(),
        buyer_name="Coastal Foods",
        destination_country="Kenya",
        shipping_date=date(2026, 11, 5),
        container_number="CONT-1042",
        status="Active",
    )
    result_sets = iter(
        [
            QueryRows(
                [
                    (
                        SimpleNamespace(
                            id=lot_id,
                            lot_code="LOT-BRB-20261104-001",
                            current_weight=Decimal("125.50"),
                            status="Available",
                        ),
                        "Yellowfin Tuna",
                    )
                ]
            ),
            QueryRows([(consignment, 2)]),
        ]
    )
    db = SimpleNamespace(
        execute=lambda statement: next(result_sets),
        scalars=lambda statement: [vessel],
    )
    _set_database_override(db)

    lots_response = authenticated_client.get("/lots?q=tuna")
    vessels_response = authenticated_client.get("/vessels")
    consignments_response = authenticated_client.get("/consignments")

    assert lots_response.status_code == 200
    assert "LOT-BRB-20261104-001" in lots_response.text
    assert "Yellowfin Tuna" in lots_response.text
    assert 'value="tuna"' in lots_response.text
    assert 'href="/trace?lot_code=LOT-BRB-20261104-001"' in lots_response.text
    assert f'href="/lots/{lot_id}"' in lots_response.text
    assert 'href="/lots" aria-current="page"' in lots_response.text

    assert vessels_response.status_code == 200
    assert "Al-Baraka" in vessels_response.text
    assert "SOM-BRB-1042" in vessels_response.text
    assert 'href="/vessels" aria-current="page"' in vessels_response.text

    assert consignments_response.status_code == 200
    assert "Coastal Foods" in consignments_response.text
    assert "CONT-1042" in consignments_response.text
    assert "2" in consignments_response.text
    assert 'href="/consignments" aria-current="page"' in consignments_response.text


def test_list_pages_redirect_unauthenticated_users(client):
    for path in ("/lots", "/vessels", "/consignments"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["location"] == "/login"


def test_public_trace_page_renders_journey_without_login(client):
    db = SimpleNamespace()
    _set_database_override(db)
    landing = SimpleNamespace(
        catch_area="Somali Basin",
        catch_date=date(2026, 11, 1),
        landing_date=date(2026, 11, 2),
    )
    vessel = SimpleNamespace(
        name="Al-Baraka",
        reg_number="SOM-BRB-1042",
        home_port="Berbera",
        owner_phone="+252000000000",
    )
    reading = SimpleNamespace(
        temp_celsius=Decimal("2.50"),
        temperature_type="Chilled",
        location="Berbera cold store",
        recorded_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
        is_breach=False,
    )
    lot = SimpleNamespace(
        lot_code="LOT-BRB-20261104-001",
        species_name="Yellowfin Tuna",
        current_weight=Decimal("125.50"),
        status="Available",
        vessel=vessel,
        catch=landing,
        processing_steps=[],
        temperature_logs=[reading],
    )
    trace = SimpleNamespace(
        lot_code="LOT-BRB-20261104-001",
        backward_lots=[lot],
        forward_consignments=[],
    )
    with patch(
        "app.main.TraceabilityService.get_trace",
        return_value=trace,
    ):
        response = client.get("/trace?lot_code=LOT-BRB-20261104-001")

    assert response.status_code == 200
    assert "LOT-BRB-20261104-001" in response.text
    assert "Product journey" in response.text
    assert "Al-Baraka" in response.text
    assert "Somali Basin" in response.text
    assert "Berbera cold store" in response.text
    assert vessel.owner_phone not in response.text


def test_public_trace_page_shows_not_found_for_unknown_code(client):
    _set_database_override(SimpleNamespace())
    with patch(
        "app.main.TraceabilityService.get_trace",
        side_effect=HTTPException(status_code=404, detail="Lot not found"),
    ):
        response = client.get("/trace?lot_code=UNKNOWN-LOT")

    assert response.status_code == 404
    assert "UNKNOWN-LOT" in response.text
    assert "No traceability record was found" in response.text


def test_lot_manage_route_accepts_database_uuid(authenticated_client):
    lot_id = uuid4()
    _set_database_override(SimpleNamespace())
    with patch(
        "app.main._render_lot_detail",
        return_value=HTMLResponse(f"<h1>{lot_id}</h1>"),
    ) as render_detail:
        response = authenticated_client.get(f"/lots/{lot_id}")

    assert response.status_code == 200
    assert str(lot_id) in response.text
    assert render_detail.call_args.args[2] == lot_id
