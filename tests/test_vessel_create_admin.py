from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4


def test_admin_can_create_vessel(client, authenticate_as):
    authenticate_as("Admin")
    vessel_id = uuid4()
    vessel = {
        "name": "Daryeel",
        "reg_number": "SOM-TEST-100",
        "license_number": "LIC-TEST-100",
        "license_expiry": date(2027, 12, 31),
        "owner_name": "Test Owner",
        "owner_phone": None,
        "home_port": "Berbera",
        "length_m": None,
        "engine_power": None,
        "gear_type": "Longline",
    }
    user = authenticate_as("Admin")
    with patch(
        "app.routes.vessels.VesselService.create_vessel",
        return_value=SimpleNamespace(id=vessel_id, **vessel),
    ) as create_vessel:
        response = client.post(
            "/vessels", json={**vessel, "license_expiry": "2027-12-31"}
        )

    assert response.status_code == 201
    assert response.json()["id"] == str(vessel_id)
    assert response.json()["name"] == "Daryeel"
    create_vessel.assert_called_once()
    assert create_vessel.call_args.args[1] == user.id
