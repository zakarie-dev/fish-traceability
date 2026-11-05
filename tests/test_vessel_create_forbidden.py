def test_non_admin_cannot_create_vessel(client, authenticate_as):
    authenticate_as("Officer")

    response = client.post(
        "/vessels",
        json={
            "name": "Daryeel",
            "reg_number": "SOM-TEST-101",
            "license_number": "LIC-TEST-101",
            "license_expiry": "2027-12-31",
            "owner_name": "Test Owner",
            "home_port": "Berbera",
            "gear_type": "Longline",
        },
    )

    assert response.status_code == 403
