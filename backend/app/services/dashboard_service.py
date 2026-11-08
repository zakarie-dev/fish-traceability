from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.repositories.dashboard_repository import DashboardRepository


@dataclass(frozen=True)
class DashboardData:
    total_catch_kg: Decimal
    active_consignments: int
    temp_alerts: int
    species_labels: list[str]
    species_weights: list[float]
    landing_site_labels: list[str]
    landing_site_weights: list[float]
    recent_lots: list[dict[str, str]]


class DashboardService:
    def __init__(self, db: Session) -> None:
        self._dashboard = DashboardRepository(db)

    def get_dashboard_data(self) -> DashboardData:
        species_rows = self._dashboard.get_available_weight_by_species()
        landing_site_rows = self._dashboard.get_available_weight_by_landing_site()
        recent_lot_rows = self._dashboard.get_recent_lots()

        return DashboardData(
            total_catch_kg=self._dashboard.get_available_lot_weight(),
            active_consignments=self._dashboard.count_consignments(),
            temp_alerts=self._dashboard.count_temperature_breaches(),
            species_labels=[name for name, _ in species_rows],
            species_weights=[float(weight) for _, weight in species_rows],
            landing_site_labels=[name for name, _ in landing_site_rows],
            landing_site_weights=[float(weight) for _, weight in landing_site_rows],
            recent_lots=[
                {
                    "lot_id": lot_code,
                    "species": species,
                    "weight": f"{weight:,.2f} kg",
                    "status": status,
                    "view_url": f"/trace?lot_code={quote(lot_code, safe='')}",
                    "detail_url": f"/lots/{lot_id}",
                }
                for lot_id, lot_code, species, weight, status in recent_lot_rows
            ],
        )
