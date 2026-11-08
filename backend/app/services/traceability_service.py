from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Consignment, Lot
from app.repositories.lot_repository import LotRepository
from app.schemas import (
    LotTraceResponse,
    RecallAffectedBuyer,
    RecallResponse,
    TraceCatch,
    TraceConsignment,
    TraceLot,
    TraceProcessingStep,
    TraceTemperatureLog,
    TraceVessel,
)


class TraceabilityService:
    """Build backward trace reports and execute transactional forward recalls."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._lots = LotRepository(db)

    def get_trace(self, lot_code: str) -> LotTraceResponse:
        """Return ancestors and their catch data plus descendant consignments.

        Args:
            lot_code: Public lot code to trace.

        Returns:
            A report containing the full upstream lot history and downstream
            consignments, including processing and temperature records.

        Raises:
            HTTPException: If no lot has the requested code.
        """
        root = self._lots.get_lot_by_code(lot_code)
        if root is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lot not found",
            )

        ancestor_ids = self._lots.get_ancestor_ids(root.id)
        descendant_ids = self._lots.get_descendant_ids(root.id)
        ancestors = self._lots.get_lots(ancestor_ids)
        species = {
            entry.id: entry for entry in self._lots.get_species(
                [lot.species_id for lot in ancestors]
            )
        }
        catches = {
            entry.id: entry
            for entry in self._lots.get_catches(
                [lot.catch_id for lot in ancestors if lot.catch_id is not None]
            )
        }
        vessels = {
            entry.id: entry
            for entry in self._lots.get_vessels(
                [catch.vessel_id for catch in catches.values()]
            )
        }
        steps_by_lot: dict[UUID, list[TraceProcessingStep]] = {}
        for step in self._lots.get_processing_steps(ancestor_ids):
            steps_by_lot.setdefault(step.lot_id, []).append(
                TraceProcessingStep(
                    id=step.id,
                    step_type=step.step_type,
                    weight_in=step.weight_in,
                    weight_out=step.weight_out,
                    yield_pct=step.yield_pct,
                )
            )
        temperatures_by_lot: dict[UUID, list[TraceTemperatureLog]] = {}
        for log in self._lots.get_temperature_logs(ancestor_ids):
            temperatures_by_lot.setdefault(log.lot_id, []).append(
                TraceTemperatureLog(
                    id=log.id,
                    temp_celsius=log.temp_celsius,
                    temperature_type=log.temperature_type,
                    recorded_at=log.recorded_at,
                    location=log.location,
                    is_breach=log.is_breach,
                )
            )

        backward_lots: list[TraceLot] = []
        for lot in sorted(ancestors, key=lambda item: item.lot_code):
            catch = catches.get(lot.catch_id) if lot.catch_id is not None else None
            vessel = vessels.get(catch.vessel_id) if catch is not None else None
            species_entry = species.get(lot.species_id)
            if species_entry is None:
                raise RuntimeError(f"Species {lot.species_id} was not found for a lot")
            backward_lots.append(
                TraceLot(
                    id=lot.id,
                    lot_code=lot.lot_code,
                    current_weight=lot.current_weight,
                    status=lot.status,
                    species_id=lot.species_id,
                    species_name=species_entry.name,
                    catch=(
                        TraceCatch(
                            id=catch.id,
                            catch_date=catch.catch_date,
                            landing_date=catch.landing_date,
                            catch_area=catch.catch_area,
                            gear_used=catch.gear_used,
                            first_temp=catch.first_temp,
                        )
                        if catch is not None
                        else None
                    ),
                    vessel=(
                        TraceVessel(
                            id=vessel.id,
                            name=vessel.name,
                            reg_number=vessel.reg_number,
                            license_number=vessel.license_number,
                            home_port=vessel.home_port,
                        )
                        if vessel is not None
                        else None
                    ),
                    processing_steps=steps_by_lot.get(lot.id, []),
                    temperature_logs=temperatures_by_lot.get(lot.id, []),
                )
            )

        consignments = self._lots.get_consignments(descendant_ids)
        return LotTraceResponse(
            lot_id=root.id,
            lot_code=root.lot_code,
            backward_lots=backward_lots,
            forward_consignments=[
                TraceConsignment(
                    id=consignment.id,
                    buyer_name=consignment.buyer_name,
                    destination_country=consignment.destination_country,
                    shipping_date=consignment.shipping_date,
                    container_number=consignment.container_number,
                    status=consignment.status,
                )
                for consignment in consignments
            ],
        )

    def recall_lot(self, lot_id: UUID) -> RecallResponse:
        """Mark the selected lot and every downstream lot and consignment recalled.

        Args:
            lot_id: UUID of the lot from which forward traversal begins.

        Returns:
            The IDs of all affected lots and each affected buyer/destination.

        Raises:
            HTTPException: If the starting lot does not exist. Database failures
                propagate and roll the entire recall transaction back.
        """
        with self._db.begin():
            starting_lots = self._lots.get_lots_for_update([lot_id])
            if not starting_lots:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lot not found",
                )
            descendant_ids = self._lots.get_descendant_ids(lot_id)
            affected_lots = self._lots.get_lots_for_update(descendant_ids)
            affected_lot_ids = [lot.id for lot in affected_lots]
            affected_consignments = self._lots.get_consignments(affected_lot_ids)

            if affected_lot_ids:
                self._db.execute(
                    update(Lot)
                    .where(Lot.id.in_(affected_lot_ids))
                    .values(status="Recalled")
                )
            if affected_consignments:
                self._db.execute(
                    update(Consignment)
                    .where(
                        Consignment.id.in_(
                            [consignment.id for consignment in affected_consignments]
                        )
                    )
                    .values(status="Recalled")
                )

            buyers = [
                RecallAffectedBuyer(
                    consignment_id=consignment.id,
                    buyer_name=consignment.buyer_name,
                    destination_country=consignment.destination_country,
                )
                for consignment in affected_consignments
            ]

        return RecallResponse(
            affected_lot_ids=affected_lot_ids,
            affected_buyers=buyers,
        )
