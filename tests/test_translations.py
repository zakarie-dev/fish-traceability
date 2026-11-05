from types import SimpleNamespace
from unittest.mock import patch

from app.translations import TRANSLATIONS


def _dashboard_data():
    return SimpleNamespace(
        total_catch_kg=0,
        active_consignments=0,
        temp_alerts=0,
        species_labels=[],
        species_weights=[],
        landing_site_labels=[],
        landing_site_weights=[],
        recent_lots=[
            {
                "lot_id": "LOT-TEST-1",
                "species": "Tuna",
                "weight": "10.00 kg",
                "status": "Available",
                "view_url": "/trace/LOT-TEST-1",
                "detail_url": "/lots/00000000-0000-0000-0000-000000000001",
            }
        ],
    )


def test_translation_dictionaries_have_matching_keys():
    assert TRANSLATIONS["en"].keys() == TRANSLATIONS["so"].keys()


def test_login_language_query_selects_somali_and_sets_cookie(client):
    response = client.get("/login?lang=so")

    assert response.status_code == 200
    assert '<html lang="so"' in response.text
    assert "Ku soo dhawoow" in response.text
    assert "Cinwaanka iimaylka" in response.text
    assert 'href="/login?lang=en"' in response.text
    assert response.cookies["lang"] == "so"


def test_login_language_cookie_is_used_and_query_takes_precedence(client):
    client.cookies.set("lang", "so")
    somali_response = client.get("/login")
    english_response = client.get("/login?lang=en")

    assert '<html lang="so"' in somali_response.text
    assert "Furaha sirta ah" in somali_response.text
    assert '<html lang="en"' in english_response.text
    assert "Welcome back" in english_response.text


def test_dashboard_language_query_translates_page_and_switch_links(
    authenticated_client,
):
    with patch(
        "app.main.DashboardService.get_dashboard_data",
        return_value=_dashboard_data(),
    ):
        response = authenticated_client.get("/dashboard?lang=so")

    assert response.status_code == 200
    assert '<html lang="so"' in response.text
    assert "Bogga guud" in response.text
    assert "Dufcadihii u dambeeyay" in response.text
    assert "Goobaha dejinta" in response.text
    assert "La heli karo" in response.text
    assert 'href="/dashboard?lang=en"' in response.text
    assert response.cookies["lang"] == "so"


def test_dashboard_language_cookie_is_used(authenticated_client):
    authenticated_client.cookies.set("lang", "so")
    with patch(
        "app.main.DashboardService.get_dashboard_data",
        return_value=_dashboard_data(),
    ):
        response = authenticated_client.get("/dashboard")

    assert response.status_code == 200
    assert '<html lang="so"' in response.text
    assert "Digniinaha heerkulka" in response.text
