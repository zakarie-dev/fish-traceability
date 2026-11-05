from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import SMSOutbox

PaymentProvider = Literal["EVC Plus", "Zaad"]


class SMSAdapter(Protocol):
    """Interface for sending an SMS through a configured transport."""

    def send_sms(self, recipient: str, message: str) -> UUID:
        """Queue a message and return its outbox identifier."""


class MockSMSAdapter:
    """Persist outgoing SMS messages without contacting an SMS provider."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def send_sms(self, recipient: str, message: str) -> UUID:
        """Write an SMS to ``sms_outbox`` and return the new message UUID."""
        outbox_id = uuid4()
        with self._db.begin():
            self._db.add(
                SMSOutbox(
                    id=outbox_id,
                    recipient=recipient,
                    message=message,
                    status="Pending",
                )
            )
        return outbox_id


@dataclass(frozen=True)
class PaymentResult:
    """Outcome returned by the mock mobile-money payment adapter."""

    success: bool
    provider: PaymentProvider
    transaction_id: str
    amount: Decimal
    currency: str
    reference: str


class PaymentAdapter(Protocol):
    """Interface for mobile-money payment providers."""

    def pay(
        self,
        provider: PaymentProvider,
        amount: Decimal,
        currency: str,
        phone_number: str,
        reference: str,
    ) -> PaymentResult:
        """Submit a payment and return its outcome."""


class MockPaymentAdapter:
    """Simulate a successful EVC Plus or Zaad payment without charging anyone."""

    def pay(
        self,
        provider: PaymentProvider,
        amount: Decimal,
        currency: str,
        phone_number: str,
        reference: str,
    ) -> PaymentResult:
        """Return a successful mock transaction for a valid positive amount."""
        if provider not in ("EVC Plus", "Zaad"):
            raise ValueError("provider must be 'EVC Plus' or 'Zaad'")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("amount must be a finite positive value")
        if not phone_number.strip():
            raise ValueError("phone_number is required")
        if not reference.strip():
            raise ValueError("reference is required")

        return PaymentResult(
            success=True,
            provider=provider,
            transaction_id=f"MOCK-{uuid4().hex.upper()}",
            amount=amount,
            currency=currency,
            reference=reference,
        )
