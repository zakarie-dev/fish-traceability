from io import BytesIO
import os
from textwrap import wrap
from urllib.parse import quote
from uuid import UUID

import qrcode
from fastapi import HTTPException, status
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Consignment, ConsignmentLot
from app.repositories.lot_repository import LotRepository


def generate_certificate_pdf(
    db: Session,
    consignment_id: UUID,
) -> bytes:
    """Generate a PDF certificate containing consignment and lot provenance.

    Args:
        db: SQLAlchemy session used to load consignment, lot, and vessel data.
        consignment_id: UUID of the consignment to certify.

    Returns:
        The generated PDF document as bytes.

    Raises:
        HTTPException: If the consignment does not exist or contains no lots.
    """
    consignment = db.scalar(
        select(Consignment).where(Consignment.id == consignment_id)
    )
    if consignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consignment not found",
        )

    lot_ids = list(
        db.scalars(
            select(ConsignmentLot.lot_id)
            .where(ConsignmentLot.consignment_id == consignment_id)
            .order_by(ConsignmentLot.lot_id)
        )
    )
    repository = LotRepository(db)
    lots = repository.get_lots(lot_ids)
    if not lots:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A certificate cannot be generated for a consignment with no lots",
        )

    source_ids_by_lot = {
        lot.id: set(repository.get_ancestor_ids(lot.id)) for lot in lots
    }
    source_lot_ids = set().union(*source_ids_by_lot.values())
    source_lots = repository.get_lots(list(source_lot_ids))
    catch_ids = [
        lot.catch_id for lot in source_lots if lot.catch_id is not None
    ]
    catches = repository.get_catches(catch_ids)
    vessels_by_id = {
        vessel.id: vessel
        for vessel in repository.get_vessels(
            [catch.vessel_id for catch in catches]
        )
    }
    vessel_ids_by_catch = {catch.id: catch.vessel_id for catch in catches}
    vessel_names_by_lot: dict[UUID, set[str]] = {}
    for source_lot in source_lots:
        if source_lot.catch_id is None:
            continue
        vessel_id = vessel_ids_by_catch.get(source_lot.catch_id)
        vessel = vessels_by_id.get(vessel_id) if vessel_id is not None else None
        if vessel is not None:
            vessel_names_by_lot.setdefault(source_lot.id, set()).add(
                f"{vessel.name} ({vessel.reg_number})"
            )

    output = BytesIO()
    document = canvas.Canvas(output, pagesize=letter)
    page_width, page_height = letter
    left = 48
    right = page_width - 48
    y = page_height - 52

    document.setTitle(f"Traceability Certificate {consignment_id}")
    document.setFont("Helvetica-Bold", 18)
    document.drawString(left, y, "Traceability Certificate")
    y -= 30

    document.setFont("Helvetica-Bold", 11)
    document.drawString(left, y, "Consignment")
    y -= 17
    document.setFont("Helvetica", 10)
    for label, value in (
        ("Buyer", consignment.buyer_name),
        ("Destination", consignment.destination_country),
        ("Shipping date", consignment.shipping_date.isoformat()),
        ("Container", consignment.container_number),
    ):
        for line in wrap(f"{label}: {value}", width=42) or [""]:
            document.drawString(left, y, line)
            y -= 15

    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    trace_url = f"{base_url}/trace/{quote(lots[0].lot_code, safe='')}"
    qr_image = qrcode.make(trace_url)
    qr_bytes = BytesIO()
    qr_image.save(qr_bytes, format="PNG")
    qr_bytes.seek(0)
    document.drawImage(
        ImageReader(qr_bytes),
        right - 104,
        page_height - 178,
        width=100,
        height=100,
        preserveAspectRatio=True,
        mask="auto",
    )
    document.setFont("Helvetica", 8)
    document.drawCentredString(right - 54, page_height - 188, "Scan to trace lot")

    y -= 8
    document.setFont("Helvetica-Bold", 11)
    document.drawString(left, y, "Lots and source vessels")
    y -= 19
    for lot in lots:
        source_ids = source_ids_by_lot[lot.id]
        source_vessels = sorted(
            {
                name
                for source_id in source_ids
                for name in vessel_names_by_lot.get(source_id, set())
            }
        )
        vessel_text = ", ".join(source_vessels) if source_vessels else "Not recorded"
        lines = [
            f"{lot.lot_code} - {lot.current_weight} kg",
            *wrap(f"Vessels: {vessel_text}", width=92),
        ]
        if y - (len(lines) * 14) < 52:
            document.showPage()
            y = page_height - 52
            document.setFont("Helvetica-Bold", 11)
            document.drawString(left, y, "Lots and source vessels (continued)")
            y -= 20
        for index, line in enumerate(lines):
            document.setFont("Helvetica-Bold" if index == 0 else "Helvetica", 9)
            document.drawString(left, y, line)
            y -= 14
        y -= 5

    document.save()
    return output.getvalue()
