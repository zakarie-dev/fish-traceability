from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    ADMIN = "Admin"
    OFFICER = "Officer"
    PROCESSOR = "Processor"
    INSPECTOR = "Inspector"
    EXPORTER = "Exporter"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    assigned_site_id: UUID | None


class VesselCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    reg_number: str = Field(min_length=1, max_length=100)
    license_number: str = Field(min_length=1, max_length=100)
    license_expiry: date
    owner_name: str = Field(min_length=1, max_length=255)
    owner_phone: str | None = Field(default=None, max_length=50)
    home_port: str = Field(min_length=1, max_length=255)
    length_m: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    engine_power: int | None = Field(default=None, gt=0)
    gear_type: str = Field(min_length=1, max_length=100)


class VesselResponse(VesselCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class LotMergeRequest(BaseModel):
    lot_ids: list[UUID] = Field(min_length=2)


class TraceVessel(BaseModel):
    id: UUID
    name: str
    reg_number: str
    license_number: str
    home_port: str


class TraceCatch(BaseModel):
    id: UUID
    catch_date: date
    landing_date: date
    catch_area: str
    gear_used: str
    first_temp: Decimal | None


class TraceProcessingStep(BaseModel):
    id: UUID
    step_type: str
    weight_in: Decimal
    weight_out: Decimal
    yield_pct: Decimal | None


class TraceTemperatureLog(BaseModel):
    id: UUID
    temp_celsius: Decimal
    temperature_type: str
    recorded_at: datetime
    location: str
    is_breach: bool


class TraceLot(BaseModel):
    id: UUID
    lot_code: str
    current_weight: Decimal
    status: str
    species_id: UUID
    species_name: str
    catch: TraceCatch | None
    vessel: TraceVessel | None
    processing_steps: list[TraceProcessingStep]
    temperature_logs: list[TraceTemperatureLog]


class TraceConsignment(BaseModel):
    id: UUID
    buyer_name: str
    destination_country: str
    shipping_date: date
    container_number: str
    status: str


class LotTraceResponse(BaseModel):
    lot_id: UUID
    lot_code: str
    backward_lots: list[TraceLot]
    forward_consignments: list[TraceConsignment]


class RecallAffectedBuyer(BaseModel):
    consignment_id: UUID
    buyer_name: str
    destination_country: str


class RecallResponse(BaseModel):
    affected_lot_ids: list[UUID]
    affected_buyers: list[RecallAffectedBuyer]
