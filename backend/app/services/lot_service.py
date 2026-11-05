from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Lot, LotLink, LotSplitLoss
from app.repositories.lot_repository import LotRepository

_CENT = Decimal("0.01")


def _weight(value: float, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid weight",
        ) from exc
    try:
        has_subcent_precision = result != result.quantize(_CENT)
    except InvalidOperation:
        has_subcent_precision = True
    if not result.is_finite() or result < 0 or has_subcent_precision:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a non-negative weight with at most 2 decimal places",
        )
    return result


def _new_lot_code(lot_id: UUID) -> str:
    return f"LOT-{lot_id.hex.upper()}"


class LotService:
    """Apply transactional split and merge operations to traceable lots."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._lots = LotRepository(db)

    def split_lot(
        self,
        parent_lot_id: UUID,
        child_weights: list[float],
        loss_weight: float,
        loss_reason: str | None = None,
    ) -> list[UUID]:
        """Split a lot into child lots while exactly accounting for all weight.

        Args:
            parent_lot_id: UUID of the lot being split.
            child_weights: Positive child-lot weights in kilograms.
            loss_weight: Processing or handling loss in kilograms.
            loss_reason: Explanation required when loss exceeds 5% of parent weight.

        Returns:
            The UUIDs of the newly created child lots, in input order.

        Raises:
            HTTPException: If the parent is missing or the requested weights violate
                split rules. Database errors propagate after the transaction rolls back.
        """
        if not child_weights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one child weight is required",
            )
        weights = [
            _weight(child_weight, f"child_weights[{index}]")
            for index, child_weight in enumerate(child_weights)
        ]
        if any(weight <= 0 for weight in weights):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Child lot weights must be greater than zero",
            )
        loss = _weight(loss_weight, "loss_weight")
        reason = loss_reason.strip() if loss_reason is not None else None
        if reason == "":
            reason = None

        with self._db.begin():
            parent = self._lots.get_lot(parent_lot_id, for_update=True)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lot not found",
                )
            parent_weight = Decimal(parent.current_weight)
            if sum(weights, loss) != parent_weight:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Child weights plus loss weight must equal the parent lot weight",
                )
            if loss > parent_weight * Decimal("0.05") and reason is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A loss reason is required when loss exceeds 5% of the parent weight",
                )

            child_lots: list[Lot] = []
            for weight in weights:
                child_id = uuid4()
                child_lots.append(
                    Lot(
                        id=child_id,
                        lot_code=_new_lot_code(child_id),
                        catch_id=parent.catch_id,
                        species_id=parent.species_id,
                        current_weight=weight,
                        status="Available",
                        parent_lot_id=parent.id,
                    )
                )
            self._lots.add_lots(child_lots)
            self._lots.add_links(
                [
                    LotLink(parent_lot_id=parent.id, child_lot_id=child.id)
                    for child in child_lots
                ]
            )
            if loss > 0:
                self._db.add(
                    LotSplitLoss(
                        parent_lot_id=parent.id,
                        loss_weight=loss,
                        loss_reason=reason,
                    )
                )
            parent.status = "Split"

        return [child.id for child in child_lots]

    def merge_lots(self, lot_ids: list[UUID]) -> UUID:
        """Merge at least two lots of the same species into a new lot.

        Args:
            lot_ids: UUIDs of all parent lots to merge.

        Returns:
            The UUID of the newly created merged lot.

        Raises:
            HTTPException: If the list is invalid, any lot is missing, or species
                differ. Database errors propagate after the transaction rolls back.
        """
        if len(lot_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least two lots are required to merge",
            )
        if len(set(lot_ids)) != len(lot_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lot IDs must be unique",
            )

        with self._db.begin():
            parents = self._lots.get_lots_for_update(lot_ids)
            if len(parents) != len(lot_ids):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="One or more lots were not found",
                )
            species_ids = {lot.species_id for lot in parents}
            if len(species_ids) != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All lots must have the same species to be merged",
                )

            merged_id = uuid4()
            merged_lot = Lot(
                id=merged_id,
                lot_code=_new_lot_code(merged_id),
                catch_id=None,
                species_id=parents[0].species_id,
                current_weight=sum(
                    (Decimal(lot.current_weight) for lot in parents), Decimal("0")
                ),
                status="Merged",
                parent_lot_id=None,
            )
            self._lots.add_lots([merged_lot])
            self._lots.add_links(
                [
                    LotLink(parent_lot_id=parent.id, child_lot_id=merged_id)
                    for parent in parents
                ]
            )
            for parent in parents:
                parent.status = "Merged"

        return merged_id
