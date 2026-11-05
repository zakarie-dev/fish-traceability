from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repositories.dashboard_repository import DashboardRepository
from app.services.dashboard_service import DashboardData


class QueryRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_dashboard_repository_uses_required_aggregates_and_filters():
    db = Mock()
    lot_id = uuid4()
    db.scalar.side_effect = [Decimal("125.50"), 3, 1]
    db.execute.side_effect = [
        QueryRows([("Lobster", Decimal("25.50"))]),
        QueryRows([("Berbera", Decimal("125.50"))]),
        QueryRows(
            [(lot_id, "LOT-123", "Lobster", Decimal("25.50"), "Available")]
        ),
    ]
    repository = DashboardRepository(db)

    assert repository.get_available_lot_weight() == Decimal("125.50")
    assert repository.count_consignments() == 3
    assert repository.count_temperature_breaches() == 1
    assert repository.get_available_weight_by_species() == [
        ("Lobster", Decimal("25.50"))
    ]
    assert repository.get_available_weight_by_landing_site() == [
        ("Berbera", Decimal("125.50"))
    ]
    assert repository.get_recent_lots() == [
        (lot_id, "LOT-123", "Lobster", Decimal("25.50"), "Available")
    ]

    compiled = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in [*db.scalar.call_args_list, *db.execute.call_args_list]
    ]
    assert "sum(lots.current_weight)" in compiled[0]
    assert "lots.status = %(status_1)s" in compiled[0]
    assert "count(consignments.id)" in compiled[1]
    assert "consignments.status = %(status_1)s" in compiled[1]
    assert "temperature_logs.is_breach IS true" in compiled[2]
    assert "species.name" in compiled[3]
    assert "landing_sites.name" in compiled[4]
    assert "catches.landing_site_id" in compiled[4]
    assert "LIMIT" in compiled[5]
    assert "LEFT OUTER JOIN catches" in compiled[5]


def test_dashboard_renders_database_metrics_and_chart_data(authenticated_client):
    dashboard_data = DashboardData(
        total_catch_kg=Decimal("12450.00"),
        active_consignments=8,
        temp_alerts=2,
        species_labels=["Lobster", "Yellowfin Tuna"],
        species_weights=[450.0, 12000.0],
        landing_site_labels=["Berbera", "Bosaso"],
        landing_site_weights=[10000.0, 2450.0],
        recent_lots=[
            {
                "lot_id": "LOT-123",
                "species": "Lobster",
                "weight": "25.50 kg",
                "status": "Available",
                "view_url": "/trace/LOT-123",
                "detail_url": f"/lots/{uuid4()}",
            }
        ],
    )
    with patch(
        "app.main.DashboardService.get_dashboard_data",
        return_value=dashboard_data,
    ):
        response = authenticated_client.get("/dashboard")

    assert response.status_code == 200
    assert "12,450.00" in response.text
    assert "Active Consignments" in response.text
    assert "[450.0, 12000.0]" in response.text
    assert '["Berbera", "Bosaso"]' in response.text
    assert "LOT-123" in response.text
    assert 'href="/trace/LOT-123"' in response.text
    assert "type: 'pie'" in response.text
    assert "type: 'bar'" in response.text


def test_dashboard_service_combines_database_metrics():
    recent_lot_id = uuid4()
    with patch("app.services.dashboard_service.DashboardRepository") as repository_type:
        repository = repository_type.return_value
        repository.get_available_lot_weight.return_value = Decimal("125.50")
        repository.count_consignments.return_value = 3
        repository.count_temperature_breaches.return_value = 1
        repository.get_available_weight_by_species.return_value = [
            ("Lobster", Decimal("25.50")),
            ("Yellowfin Tuna", Decimal("100.00")),
        ]
        repository.get_available_weight_by_landing_site.return_value = [
            ("Berbera", Decimal("75.50")),
            ("Bosaso", Decimal("50.00")),
        ]
        repository.get_recent_lots.return_value = [
            (
                recent_lot_id,
                "LOT-123",
                "Lobster",
                Decimal("25.50"),
                "Available",
            )
        ]

        from app.services.dashboard_service import DashboardService

        dashboard = DashboardService(object()).get_dashboard_data()

    assert dashboard.total_catch_kg == Decimal("125.50")
    assert dashboard.active_consignments == 3
    assert dashboard.temp_alerts == 1
    assert dashboard.species_labels == ["Lobster", "Yellowfin Tuna"]
    assert dashboard.species_weights == [25.5, 100.0]
    assert dashboard.landing_site_labels == ["Berbera", "Bosaso"]
    assert dashboard.landing_site_weights == [75.5, 50.0]
    assert dashboard.recent_lots == [
        {
            "lot_id": "LOT-123",
            "species": "Lobster",
            "weight": "25.50 kg",
            "status": "Available",
            "view_url": "/trace/LOT-123",
            "detail_url": f"/lots/{recent_lot_id}",
        }
    ]
