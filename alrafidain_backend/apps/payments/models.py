from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from apps.common.models import BaseModel


class Wallet(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet",
    )
    currency = models.CharField(max_length=10, default="IQD")
    cached_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Wallet {self.user_id} ({self.currency})"


class WalletTransaction(BaseModel):
    class TransactionType(models.TextChoices):
        MANUAL_RECHARGE = "manual_recharge", "Manual Recharge"
        PAYMENT = "payment", "Payment"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"
        HOLD = "hold", "Hold"
        RELEASE = "release", "Release"

    class Direction(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="IQD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reference_type = models.CharField(max_length=100, blank=True, null=True)
    reference_id = models.UUIDField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "status", "created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({"amount": "Amount must be positive."})

    def __str__(self):
        return f"{self.transaction_type}:{self.direction}:{self.amount}"


class PlatformFeeRule(BaseModel):
    class ServiceType(models.TextChoices):
        CONSULTATION = "consultation", "Consultation"
        PHARMACY_REQUEST = "pharmacy_request", "Pharmacy Request"
        LAB_REQUEST = "lab_request", "Lab Request"

    class FeeType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed"

    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    fee_type = models.CharField(max_length=20, choices=FeeType.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="IQD")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service_type"],
                condition=Q(is_active=True),
                name="uniq_active_platform_fee_rule_per_service_type",
            )
        ]

    def clean(self):
        if self.value is None:
            raise ValidationError({"value": "Value is required."})
        if self.fee_type == self.FeeType.PERCENTAGE and (self.value < 0 or self.value > 100):
            raise ValidationError({"value": "Percentage fee must be between 0 and 100."})
        if self.fee_type == self.FeeType.FIXED and self.value < 0:
            raise ValidationError({"value": "Fixed fee cannot be negative."})

    def __str__(self):
        return f"{self.service_type}:{self.fee_type}:{self.value}"


class PaymentIntent(BaseModel):
    class ServiceType(models.TextChoices):
        CONSULTATION = "consultation", "Consultation"
        PHARMACY_REQUEST = "pharmacy_request", "Pharmacy Request"
        LAB_REQUEST = "lab_request", "Lab Request"
        WALLET_RECHARGE = "wallet_recharge", "Wallet Recharge"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentMethod(models.TextChoices):
        WALLET = "wallet", "Wallet"
        GATEWAY = "gateway", "Gateway"
        MANUAL = "manual", "Manual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_intents",
    )
    wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True)
    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    reference_id = models.UUIDField(blank=True, null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="IQD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    provider = models.CharField(max_length=50, blank=True, null=True)
    provider_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    external_reference_id = models.CharField(max_length=255, blank=True, null=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    refunded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "created_at"]),
            models.Index(fields=["service_type", "reference_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["service_type", "reference_id"],
                condition=Q(status="succeeded") & Q(reference_id__isnull=False),
                name="uniq_succeeded_payment_per_service_reference",
            )
        ]

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({"amount": "Amount must be positive."})

    def __str__(self):
        return f"Intent {self.id} ({self.status})"


class ProviderEarning(BaseModel):
    class ProviderType(models.TextChoices):
        DOCTOR = "doctor", "Doctor"
        PHARMACY = "pharmacy", "Pharmacy"
        LAB = "lab", "Lab"

    class ServiceType(models.TextChoices):
        CONSULTATION = "consultation", "Consultation"
        PHARMACY_REQUEST = "pharmacy_request", "Pharmacy Request"
        LAB_REQUEST = "lab_request", "Lab Request"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AVAILABLE = "available", "Available"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    provider_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    reference_id = models.UUIDField()
    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_earnings",
    )
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    platform_fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="IQD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    metadata = models.JSONField(default=dict, blank=True)
    available_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service_type", "reference_id"],
                name="uniq_provider_earning_per_service_reference",
            )
        ]
        indexes = [
            models.Index(fields=["provider_user", "status", "created_at"]),
            models.Index(fields=["service_type", "reference_id"]),
        ]

    def clean(self):
        if self.gross_amount is None or self.gross_amount < 0:
            raise ValidationError({"gross_amount": "Gross amount cannot be negative."})
        if self.platform_fee_amount is None or self.platform_fee_amount < 0:
            raise ValidationError({"platform_fee_amount": "Platform fee amount cannot be negative."})
        if self.net_amount is None or self.net_amount < 0:
            raise ValidationError({"net_amount": "Net amount cannot be negative."})
        if self.net_amount != (self.gross_amount - self.platform_fee_amount):
            raise ValidationError({"net_amount": "Net amount must equal gross amount minus platform fee."})

    def __str__(self):
        return f"Earning {self.provider_type}:{self.net_amount}"


def confirmed_wallet_balance(wallet: Wallet) -> Decimal:
    totals = wallet.transactions.filter(status=WalletTransaction.Status.CONFIRMED).aggregate(
        credits=Sum(
            "amount",
            filter=Q(direction=WalletTransaction.Direction.CREDIT),
            default=Decimal("0.00"),
        ),
        debits=Sum(
            "amount",
            filter=Q(direction=WalletTransaction.Direction.DEBIT),
            default=Decimal("0.00"),
        ),
    )
    return (totals["credits"] or Decimal("0.00")) - (totals["debits"] or Decimal("0.00"))
