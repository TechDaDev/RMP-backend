from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from apps.common.models import BaseModel


class PharmacyPrescriptionRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUOTED = "quoted", "Quoted"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAYMENT_PENDING = "payment_pending", "Payment Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    prescription = models.ForeignKey(
        "prescriptions.Prescription",
        on_delete=models.PROTECT,
        related_name="pharmacy_requests",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pharmacy_prescription_requests",
    )
    pharmacy = models.ForeignKey(
        "profiles.PharmacistProfile",
        on_delete=models.PROTECT,
        related_name="prescription_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_pharmacy_prescriptions",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="IQD")
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    payment_intent = models.ForeignKey(
        "payments.PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_failed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    pharmacy_notes = models.TextField(blank=True, null=True)
    patient_notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    rejected_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["prescription", "pharmacy"]),
            models.Index(fields=["patient", "created_at"]),
            models.Index(fields=["payment_status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["prescription", "pharmacy"],
                condition=Q(status__in=["pending", "quoted"]),
                name="uniq_active_pending_quoted_prescription_pharmacy_request",
            )
        ]

    @property
    def is_active_request(self):
        return self.status in {self.Status.PENDING, self.Status.QUOTED, self.Status.ACCEPTED}

    @property
    def can_be_quoted(self):
        return self.status in {self.Status.PENDING, self.Status.QUOTED}

    @property
    def can_be_accepted(self):
        return self.status == self.Status.QUOTED

    @property
    def can_be_rejected(self):
        return self.status == self.Status.QUOTED

    def recalculate_total_price(self):
        aggregate = self.items.aggregate(total=Sum("total_price"))
        self.total_price = aggregate["total"] or Decimal("0.00")
        return self.total_price

    def clean(self):
        if self.patient_id and self.prescription_id and self.patient_id != self.prescription.patient_id:
            raise ValidationError({"patient": "Patient must match prescription patient."})

    def __str__(self):
        return f"Request {self.id} ({self.status})"


class PharmacyPrescriptionRequestItem(BaseModel):
    class AvailabilityStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AVAILABLE = "available", "Available"
        UNAVAILABLE = "unavailable", "Unavailable"
        SUBSTITUTED = "substituted", "Substituted"

    request = models.ForeignKey(
        PharmacyPrescriptionRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    prescription_item = models.ForeignKey(
        "prescriptions.PrescriptionItem",
        on_delete=models.PROTECT,
        related_name="pharmacy_request_items",
    )
    inventory_item = models.ForeignKey(
        "pharmacy_inventory.PharmacyDrugInventory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_items",
    )
    requested_name_snapshot = models.CharField(max_length=255)
    quoted_name = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.PENDING,
    )
    substitution_note = models.TextField(blank=True, null=True)
    pharmacy_note = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["request", "availability_status"]),
            models.Index(fields=["prescription_item"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "prescription_item"],
                name="uniq_request_prescription_item",
            )
        ]

    def clean(self):
        if self.availability_status == self.AvailabilityStatus.UNAVAILABLE:
            self.unit_price = Decimal("0.00")
            self.total_price = Decimal("0.00")
        else:
            if self.quantity < 1:
                raise ValidationError({"quantity": "Quantity must be at least 1."})
            if self.unit_price < 0:
                raise ValidationError({"unit_price": "Unit price cannot be negative."})
            self.total_price = self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        if self.availability_status == self.AvailabilityStatus.UNAVAILABLE:
            self.unit_price = Decimal("0.00")
            self.total_price = Decimal("0.00")
        else:
            self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.requested_name_snapshot} ({self.availability_status})"
