"""Seed a coherent, demo-only fish traceability workflow.

Run from the repository root with:
    python backend\\seed_demo_data.py --confirm

The script uses backend/.env and DATABASE_URL. It never deletes records. Keep
the configured database URL pointed at a demo/development database.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.adapters import MockPaymentAdapter, MockSMSAdapter, PaymentProvider
from app.database import SessionLocal
from app.models import (
    AuditLog,
    Catch,
    Consignment,
    ConsignmentLot,
    Inspection,
    LandingSite,
    Lot,
    LotLink,
    PaymentTransaction,
    ProcessingStep,
    SMSOutbox,
    Species,
    TemperatureLog,
    User,
    Vessel,
)

SEED_MARKER = "Demo showcase catch"
SEED_LOT_PREFIX = "LOT-DEMO-SHOWCASE-"
SEED_CONSIGNMENT_PREFIX = "DEMO-SHOWCASE-"
SEED_PAYMENT_PREFIX = "DEMO-PAY-"
RANDOM_SEED = 20261108

SITE_DATA = (
    ("Berbera", "Somaliland", Decimal("10.439600"), Decimal("45.014300")),
    ("Bosaso", "Puntland", Decimal("11.284200"), Decimal("49.181600")),
    ("Mogadishu", "Banaadir", Decimal("2.046900"), Decimal("45.318200")),
    ("Kismayo", "Jubaland", Decimal("-0.354700"), Decimal("42.545400")),
)

VESSEL_DATA = (
    (
        "Al-Baraka",
        "SOM-BRB-1042",
        "LIC-BRB-DEMO-1042",
        "Abdi Hassan",
        "+252 63 555 0101",
        "Berbera",
        Decimal("18.50"),
        450,
        "Longline",
    ),
    (
        "Hilaac",
        "SOM-BOS-2088",
        "LIC-BOS-DEMO-2088",
        "Amina Mohamed",
        "+252 90 555 0202",
        "Bosaso",
        Decimal("14.20"),
        320,
        "Gillnet",
    ),
    (
        "Badda-Cad",
        "SOM-MOG-3015",
        "LIC-MOG-DEMO-3015",
        "Hassan Ali",
        "+252 61 555 0303",
        "Mogadishu",
        Decimal("20.00"),
        520,
        "Purse seine",
    ),
)

SPECIES_DATA = (
    ("Tuna", False),
    ("Kingfish", False),
    ("Lobster", True),
)

CONSIGNMENT_DATA = (
    ("Gulf Seafood LLC", "UAE", "DEMO-SHOWCASE-UAE-001"),
    ("Riyadh Imports", "Saudi Arabia", "DEMO-SHOWCASE-SAU-002"),
    ("Muscat Trading", "Oman", "DEMO-SHOWCASE-OMN-003"),
)


def _require_users(db: Session) -> dict[str, User]:
    users = list(db.scalars(select(User).order_by(User.email)))
    required_roles = ("Admin", "Officer", "Processor", "Inspector")
    by_role: dict[str, list[User]] = {role: [] for role in required_roles}
    for user in users:
        if user.role in by_role:
            by_role[user.role].append(user)

    missing = [role for role, matches in by_role.items() if not matches]
    if missing:
        raise RuntimeError(
            "Missing demo users for roles: "
            + ", ".join(missing)
            + ". Apply backend/migrations/002_seed.sql first."
        )
    return {role: matches[0] for role, matches in by_role.items()}


def _get_or_add_infrastructure(
    db: Session,
) -> tuple[list[LandingSite], list[Vessel], list[Species]]:
    sites_by_name = {
        site.name: site for site in db.scalars(select(LandingSite))
    }
    sites: list[LandingSite] = []
    for name, region, latitude, longitude in SITE_DATA:
        site = sites_by_name.get(name)
        if site is None:
            site = LandingSite(
                name=name,
                region=region,
                gps_lat=latitude,
                gps_lng=longitude,
                is_active=True,
            )
            db.add(site)
            sites_by_name[name] = site
        sites.append(site)

    vessels_by_name = {vessel.name: vessel for vessel in db.scalars(select(Vessel))}
    vessels: list[Vessel] = []
    site_names = {site.name for site in sites}
    for (
        name,
        reg_number,
        license_number,
        owner_name,
        owner_phone,
        home_port,
        length_m,
        engine_power,
        gear_type,
    ) in VESSEL_DATA:
        vessel = vessels_by_name.get(name)
        if vessel is None:
            existing_registration = db.scalar(
                select(Vessel).where(Vessel.reg_number == reg_number)
            )
            existing_license = db.scalar(
                select(Vessel).where(Vessel.license_number == license_number)
            )
            if existing_registration is not None or existing_license is not None:
                raise RuntimeError(
                    f"Vessel registration/license for {name} is already assigned "
                    "to a differently named vessel."
                )
            if home_port not in site_names:
                raise RuntimeError(f"No landing site exists for vessel {name}.")
            vessel = Vessel(
                name=name,
                reg_number=reg_number,
                license_number=license_number,
                license_expiry=date.today() + timedelta(days=365),
                owner_name=owner_name,
                owner_phone=owner_phone,
                home_port=home_port,
                length_m=length_m,
                engine_power=engine_power,
                gear_type=gear_type,
            )
            db.add(vessel)
            vessels_by_name[name] = vessel
        vessels.append(vessel)

    species_by_name = {
        species.name: species for species in db.scalars(select(Species))
    }
    species: list[Species] = []
    for name, is_protected in SPECIES_DATA:
        entry = species_by_name.get(name)
        if entry is None:
            entry = Species(name=name, is_protected=is_protected)
            db.add(entry)
            species_by_name[name] = entry
        species.append(entry)

    db.flush()
    return sites, vessels, species


def _already_seeded(db: Session) -> bool:
    seed_catches = list(
        db.scalars(
            select(Catch).where(Catch.catch_area.like(f"{SEED_MARKER} %"))
        )
    )
    if not seed_catches:
        return False
    if len(seed_catches) != 15:
        raise RuntimeError(
            f"Found {len(seed_catches)} showcase catches, not 15. "
            "Refusing to add duplicate or partial demo data."
        )

    catch_ids = [catch.id for catch in seed_catches]
    linked_lot_count = db.scalar(
        select(func.count(Lot.id)).where(Lot.catch_id.in_(catch_ids))
    )
    merged_lot_count = db.scalar(
        select(func.count(Lot.id)).where(
            Lot.lot_code.like(f"{SEED_LOT_PREFIX}%-MERGED")
        )
    )
    consignment_count = db.scalar(
        select(func.count(Consignment.id)).where(
            Consignment.container_number.like(f"{SEED_CONSIGNMENT_PREFIX}%")
        )
    )
    payment_count = db.scalar(
        select(func.count(PaymentTransaction.id)).where(
            PaymentTransaction.reference.like(f"{SEED_PAYMENT_PREFIX}%")
        )
    )
    sms_count = db.scalar(
        select(func.count(SMSOutbox.id)).where(
            SMSOutbox.message.like("Demo showcase:%")
        )
    )
    if (
        linked_lot_count == 25
        and merged_lot_count == 1
        and consignment_count == 3
        and payment_count == 3
        and sms_count == 5
    ):
        return True
    raise RuntimeError(
        "Showcase catch records exist but the complete demo workflow was not "
        "found. Refusing to duplicate data; inspect the demo database first."
    )


def seed_demo_data(db: Session) -> bool:
    """Insert the complete showcase workflow atomically; return False if present."""
    inspector = inspect(db.get_bind())
    required_tables = {
        "payment_transactions",
        "sms_outbox",
        "lot_links",
        "lot_split_losses",
        "audit_log",
    }
    missing_tables = sorted(
        table_name for table_name in required_tables
        if not inspector.has_table(table_name)
    )
    if missing_tables:
        raise RuntimeError(
            "Required tables are missing: "
            + ", ".join(missing_tables)
            + ". Apply migrations 004, 005, and 007 before seeding."
        )
    temperature_columns = {
        column["name"]
        for column in inspector.get_columns("temperature_logs")
    }
    inspection_columns = {
        column["name"] for column in inspector.get_columns("inspections")
    }
    if "temperature_type" not in temperature_columns or (
        "inspected_at" not in inspection_columns
    ):
        raise RuntimeError(
            "Required temperature/inspection columns are missing. "
            "Apply migrations 005 and 006 before seeding."
        )

    with db.begin():
        if _already_seeded(db):
            return False

        users = _require_users(db)
        sites, vessels, species = _get_or_add_infrastructure(db)
        randomizer = random.Random(RANDOM_SEED)
        today = date.today()
        catches: list[Catch] = []
        parent_lots: list[Lot] = []

        for index in range(15):
            days_ago = randomizer.randint(2, 89)
            catch_date = today - timedelta(days=days_ago)
            landing_date = catch_date + timedelta(days=randomizer.randint(0, 2))
            landing_site = sites[index % len(sites)]
            vessel = vessels[index % len(vessels)]
            officer = users["Officer"]
            catch = Catch(
                id=uuid4(),
                vessel_id=vessel.id,
                officer_id=officer.id,
                landing_site_id=landing_site.id,
                catch_date=catch_date,
                landing_date=landing_date,
                catch_area=f"{SEED_MARKER} {index + 1:02d} - {landing_site.region}",
                gear_used=vessel.gear_type,
                first_temp=Decimal("-1.50"),
            )
            lot_id = uuid4()
            weight = Decimal(randomizer.randint(50, 500))
            lot = Lot(
                id=lot_id,
                lot_code=f"{SEED_LOT_PREFIX}{today:%Y%m%d}-{index + 1:03d}",
                catch_id=catch.id,
                species_id=species[index % len(species)].id,
                current_weight=weight,
                status="Available",
                parent_lot_id=None,
            )
            db.add_all([catch, lot])
            catches.append(catch)
            parent_lots.append(lot)

        db.flush()

        children_by_parent: dict[UUID, list[Lot]] = {}
        for index, parent in enumerate(parent_lots[:5]):
            first_weight = (
                Decimal(parent.current_weight) / Decimal("2")
            ).quantize(Decimal("0.01"))
            second_weight = Decimal(parent.current_weight) - first_weight
            if first_weight + second_weight != Decimal(parent.current_weight):
                raise RuntimeError("Split weights do not conserve parent weight.")
            children = [
                Lot(
                    id=uuid4(),
                    lot_code=f"{SEED_LOT_PREFIX}{today:%Y%m%d}-S{index + 1:02d}-{part}",
                    catch_id=parent.catch_id,
                    species_id=parent.species_id,
                    current_weight=child_weight,
                    status="Available",
                    parent_lot_id=parent.id,
                )
                for part, child_weight in enumerate(
                    (first_weight, second_weight), start=1
                )
            ]
            db.add_all(children)
            db.add_all(
                [
                    LotLink(parent_lot_id=parent.id, child_lot_id=child.id)
                    for child in children
                ]
            )
            parent.status = "Split"
            children_by_parent[parent.id] = children

        first_split_parent = parent_lots[0]
        merge_sources = children_by_parent[first_split_parent.id]
        merged_id = uuid4()
        merged_lot = Lot(
            id=merged_id,
            lot_code=f"{SEED_LOT_PREFIX}{today:%Y%m%d}-MERGED",
            catch_id=None,
            species_id=merge_sources[0].species_id,
            current_weight=sum(
                (Decimal(lot.current_weight) for lot in merge_sources),
                Decimal("0"),
            ),
            status="Available",
            parent_lot_id=None,
        )
        db.add(merged_lot)
        db.add_all(
            [
                LotLink(parent_lot_id=source.id, child_lot_id=merged_id)
                for source in merge_sources
            ]
        )
        for source in merge_sources:
            source.status = "Merged"

        temperature_times: dict[UUID, datetime] = {}
        for index, lot in enumerate(parent_lots):
            landed_at = datetime.combine(
                catches[index].landing_date,
                time(hour=12),
                tzinfo=timezone.utc,
            )
            is_breach = index < 2
            reading = TemperatureLog(
                id=uuid4(),
                lot_id=lot.id,
                temp_celsius=Decimal("8.00") if is_breach else Decimal("-20.00"),
                temperature_type="Chilled" if is_breach else "Frozen",
                recorded_at=landed_at,
                location=f"{sites[index % len(sites)].name} cold storage",
                is_breach=is_breach,
            )
            db.add(reading)
            temperature_times[lot.id] = landed_at

        for lot in parent_lots[10:15]:
            input_weight = Decimal(lot.current_weight)
            output_weight = (input_weight * Decimal("0.88")).quantize(
                Decimal("0.01")
            )
            db.add(
                ProcessingStep(
                    id=uuid4(),
                    lot_id=lot.id,
                    step_type="Filleting",
                    operator_id=users["Processor"].id,
                    weight_in=input_weight,
                    weight_out=output_weight,
                    yield_pct=(output_weight / input_weight * 100).quantize(
                        Decimal("0.01")
                    ),
                )
            )

        passed_lots: list[Lot] = []
        for index, lot in enumerate(parent_lots[5:11], start=5):
            inspected_at = temperature_times[lot.id] + timedelta(hours=4)
            passed = index >= 7
            inspection = Inspection(
                id=uuid4(),
                lot_id=lot.id,
                inspector_id=users["Inspector"].id,
                grade=("A" if index % 2 else "B") if passed else "C",
                passed=passed,
                inspected_at=inspected_at,
                notes=(
                    "Cold-chain breach; hold for review."
                    if not passed
                    else "Quality checks passed."
                ),
            )
            db.add(inspection)
            if passed:
                passed_lots.append(lot)

        for index, (buyer, destination, container_number) in enumerate(
            CONSIGNMENT_DATA
        ):
            assigned_lot = passed_lots[index]
            consignment = Consignment(
                id=uuid4(),
                buyer_name=buyer,
                destination_country=destination,
                shipping_date=today + timedelta(days=7 + index),
                container_number=container_number,
                is_locked=False,
                status="Active",
            )
            db.add(consignment)
            db.add(
                ConsignmentLot(
                    consignment_id=consignment.id,
                    lot_id=assigned_lot.id,
                )
            )
            db.add(
                AuditLog(
                    id=uuid4(),
                    user_id=users["Admin"].id,
                    action="consignment.create",
                    entity_id=consignment.id,
                )
            )

        payment_adapter = MockPaymentAdapter()
        payment_data: tuple[tuple[PaymentProvider, Decimal, Vessel, str], ...] = (
            ("EVC Plus", Decimal("500.00"), vessels[0], VESSEL_DATA[0][4]),
            ("Zaad", Decimal("325.00"), vessels[1], VESSEL_DATA[1][4]),
            ("EVC Plus", Decimal("750.00"), vessels[2], VESSEL_DATA[2][4]),
        )
        for index, (provider, amount, vessel, phone_number) in enumerate(
            payment_data,
            start=1,
        ):
            phone_number = vessel.owner_phone or phone_number
            payment = payment_adapter.pay(
                provider=provider,
                amount=amount,
                currency="USD",
                phone_number=phone_number,
                reference=f"{SEED_PAYMENT_PREFIX}{index:02d}",
            )
            db.add(
                PaymentTransaction(
                    id=uuid4(),
                    user_id=users["Admin"].id,
                    provider=payment.provider,
                    phone_number=phone_number,
                    amount=payment.amount,
                    currency=payment.currency,
                    reference=payment.reference,
                    transaction_id=payment.transaction_id,
                    status="Successful",
                )
            )
            MockSMSAdapter(db).send_sms(
                recipient=phone_number,
                message=(
                    f"Demo showcase: Payment of ${payment.amount:.2f} received "
                    f"via {payment.provider}. Reference: {payment.reference}."
                ),
            )

        for lot in passed_lots[:2]:
            vessel_index = parent_lots.index(lot) % len(vessels)
            phone_number = (
                vessels[vessel_index].owner_phone
                or VESSEL_DATA[vessel_index][4]
            )
            MockSMSAdapter(db).send_sms(
                recipient=phone_number,
                message=f"Demo showcase: Inspection passed for Lot {lot.lot_code}.",
            )

        db.flush()

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm that DATABASE_URL points to a demo/development database",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error(
            "refusing to write demo data without --confirm; verify DATABASE_URL "
            "points to a demo/development database"
        )

    with SessionLocal() as db:
        created = seed_demo_data(db)
    if created:
        print("Demo data seeded successfully!")
    else:
        print("Demo data already present; no records were added.")


if __name__ == "__main__":
    main()
