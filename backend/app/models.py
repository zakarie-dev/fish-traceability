from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LandingSite(Base):
    __tablename__ = "landing_sites"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    region: Mapped[str] = mapped_column(String, nullable=False)
    gps_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    gps_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Admin', 'Officer', 'Processor', 'Inspector', 'Exporter')",
            name="users_role_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    assigned_site_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("landing_sites.id", ondelete="SET NULL"),
        nullable=True,
    )


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    reg_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    license_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    license_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    home_port: Mapped[str] = mapped_column(String, nullable=False)
    length_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    engine_power: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gear_type: Mapped[str] = mapped_column(String, nullable=False)


class Species(Base):
    __tablename__ = "species"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    is_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Catch(Base):
    __tablename__ = "catches"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    vessel_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("vessels.id"), nullable=False
    )
    officer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    landing_site_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("landing_sites.id"), nullable=False
    )
    catch_date: Mapped[date] = mapped_column(Date, nullable=False)
    landing_date: Mapped[date] = mapped_column(Date, nullable=False)
    catch_area: Mapped[str] = mapped_column(String, nullable=False)
    gear_used: Mapped[str] = mapped_column(String, nullable=False)
    first_temp: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    lot_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    catch_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("catches.id"), nullable=True
    )
    species_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("species.id"), nullable=False
    )
    current_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    parent_lot_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("lots.id"), nullable=True
    )


class LotLink(Base):
    __tablename__ = "lot_links"

    parent_lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        primary_key=True,
    )


class LotSplitLoss(Base):
    __tablename__ = "lot_split_losses"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    parent_lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("lots.id", ondelete="CASCADE")
    )
    loss_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    loss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessingStep(Base):
    __tablename__ = "processing_steps"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("lots.id", ondelete="CASCADE")
    )
    step_type: Mapped[str] = mapped_column(String, nullable=False)
    operator_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    weight_in: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    weight_out: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)


class TemperatureLog(Base):
    __tablename__ = "temperature_logs"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("lots.id", ondelete="CASCADE")
    )
    temp_celsius: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    location: Mapped[str] = mapped_column(String, nullable=False)
    is_breach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("lots.id", ondelete="CASCADE")
    )
    inspector_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    grade: Mapped[str] = mapped_column(String, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)


class Consignment(Base):
    __tablename__ = "consignments"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    buyer_name: Mapped[str] = mapped_column(String, nullable=False)
    destination_country: Mapped[str] = mapped_column(String, nullable=False)
    shipping_date: Mapped[date] = mapped_column(Date, nullable=False)
    container_number: Mapped[str] = mapped_column(String, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Active")


class ConsignmentLot(Base):
    __tablename__ = "consignment_lots"

    consignment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("consignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class SMSOutbox(Base):
    __tablename__ = "sms_outbox"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    recipient: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
