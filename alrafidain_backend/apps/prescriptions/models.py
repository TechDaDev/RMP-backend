import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.choices import (
    ConsultationStatus,
    DispensingAttemptStatus,
    MedicationRoute,
    PrescriptionItemStatus,
    PrescriptionStatus,
    UserType,
    VerificationStatus,
)
from apps.common.models import BaseModel

PRESCRIPTION_EXPIRY_DAYS = getattr(settings, "PRESCRIPTION_EXPIRY_DAYS", 7)


class Prescription(BaseModel):
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_prescriptions",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="patient_prescriptions",
    )
    status = models.CharField(
        max_length=30,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.ISSUED,
    )
    qr_token = models.CharField(max_length=64, unique=True, editable=False)
    qr_token_created_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    fully_dispensed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Prescription {self.id} [{self.status}]"

    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def is_locked(self) -> bool:
        return self.status in (
            PrescriptionStatus.FULLY_DISPENSED,
            PrescriptionStatus.EXPIRED,
            PrescriptionStatus.CANCELLED,
        )

    def has_pending_items(self) -> bool:
        return self.items.filter(status=PrescriptionItemStatus.PENDING).exists()

    def update_status_from_items(self):
        now = timezone.now()
        if self.is_expired() and self.status not in (
            PrescriptionStatus.CANCELLED,
            PrescriptionStatus.FULLY_DISPENSED,
        ):
            self.status = PrescriptionStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])
            return

        if self.status == PrescriptionStatus.CANCELLED:
            return

        items = list(self.items.all())
        if not items:
            return

        statuses = {item.status for item in items}
        all_done = statuses <= {PrescriptionItemStatus.DISPENSED, PrescriptionItemStatus.CANCELLED}
        any_dispensed = PrescriptionItemStatus.DISPENSED in statuses
        any_pending = PrescriptionItemStatus.PENDING in statuses

        if all_done and any_dispensed:
            self.status = PrescriptionStatus.FULLY_DISPENSED
            self.fully_dispensed_at = now
            self.save(update_fields=["status", "fully_dispensed_at", "updated_at"])
        elif any_dispensed and any_pending:
            self.status = PrescriptionStatus.PARTIALLY_DISPENSED
            self.save(update_fields=["status", "updated_at"])
        elif not any_dispensed and not any_pending:
            # All items cancelled with none dispensed
            self.status = PrescriptionStatus.CANCELLED
            self.cancelled_at = now
            self.save(update_fields=["status", "cancelled_at", "updated_at"])

    def clean(self):
        valid_statuses = {ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED}
        if self.consultation.status not in valid_statuses:
            raise ValidationError("Prescription can only be created for accepted or doctor_responded consultations.")
        if self.doctor_id != self.consultation.assigned_doctor_id:
            raise ValidationError("Only the assigned doctor can create a prescription for this consultation.")
        if self.patient_id != self.consultation.patient_id:
            raise ValidationError("Patient must match the consultation patient.")
        if self.doctor.user_type != UserType.DOCTOR:
            raise ValidationError("Prescriber must be a doctor.")
        if self.patient.user_type != UserType.PATIENT:
            raise ValidationError("Recipient must be a patient.")

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = _generate_unique_qr_token()
            self.qr_token_created_at = timezone.now()
        if not self.expires_at:
            self.expires_at = (self.qr_token_created_at or timezone.now()) + timedelta(days=PRESCRIPTION_EXPIRY_DAYS)
        super().save(*args, **kwargs)


def _generate_unique_qr_token() -> str:
    for _ in range(10):
        token = secrets.token_urlsafe(32)
        if not Prescription.objects.filter(qr_token=token).exists():
            return token
    raise RuntimeError("Could not generate a unique QR token.")


class PrescriptionItem(BaseModel):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    medication_name = models.CharField(max_length=200)
    strength = models.CharField(max_length=100, blank=True)
    dosage = models.CharField(max_length=200)
    frequency = models.CharField(max_length=200)
    duration = models.CharField(max_length=200)
    route = models.CharField(max_length=20, choices=MedicationRoute.choices)
    quantity = models.CharField(max_length=100, blank=True)
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=PrescriptionItemStatus.choices,
        default=PrescriptionItemStatus.PENDING,
    )
    dispensed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.medication_name} [{self.status}]"


class DispensingRecord(BaseModel):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="dispensing_records",
    )
    prescription_item = models.ForeignKey(
        PrescriptionItem,
        on_delete=models.CASCADE,
        related_name="dispensing_records",
    )
    pharmacist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dispensing_records",
    )
    status = models.CharField(max_length=20, choices=DispensingAttemptStatus.choices)
    dispensed_quantity = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"DispensingRecord {self.id} [{self.status}]"

    def clean(self):
        if self.pharmacist.user_type != UserType.PHARMACIST:
            raise ValidationError("Only pharmacists can create dispensing records.")
        try:
            approved = self.pharmacist.pharmacist_profile.verification_status == VerificationStatus.APPROVED
        except Exception:
            approved = False
        if not approved:
            raise ValidationError("Pharmacist must be approved to dispense.")
        if self.prescription.is_locked():
            raise ValidationError("Cannot dispense a locked prescription.")
        if self.prescription_item.prescription_id != self.prescription_id:
            raise ValidationError("Prescription item does not belong to this prescription.")
