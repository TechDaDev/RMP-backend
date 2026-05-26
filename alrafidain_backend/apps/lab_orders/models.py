import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.choices import (
    BloodGroup,
    ConsultationStatus,
    LabCompletionAttemptStatus,
    LabOrderItemStatus,
    LabOrderStatus,
    LabResultFlag,
    LabResultStatus,
    LabResultValueType,
    LabTestCategory,
    UserType,
    VerificationStatus,
)
from apps.common.models import BaseModel
from apps.common.upload_paths import lab_result_file_upload_path

LAB_ORDER_EXPIRY_DAYS = getattr(settings, "LAB_ORDER_EXPIRY_DAYS", 7)


class LabTestCatalog(BaseModel):
    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=30, choices=LabTestCategory.choices)
    code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    default_sample_type = models.CharField(max_length=100, blank=True)
    default_instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class LabOrder(BaseModel):
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.PROTECT,
        related_name="lab_orders",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_lab_orders",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="patient_lab_orders",
    )
    status = models.CharField(
        max_length=30,
        choices=LabOrderStatus.choices,
        default=LabOrderStatus.ISSUED,
    )
    qr_token = models.CharField(max_length=64, unique=True, editable=False)
    qr_token_created_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    fully_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["doctor", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"LabOrder {self.id} [{self.status}]"

    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def is_locked(self) -> bool:
        return self.status in (
            LabOrderStatus.FULLY_COMPLETED,
            LabOrderStatus.EXPIRED,
            LabOrderStatus.CANCELLED,
        )

    def has_pending_items(self) -> bool:
        return self.items.filter(status=LabOrderItemStatus.PENDING).exists()

    def update_status_from_items(self):
        now = timezone.now()
        if self.is_expired() and self.status not in (
            LabOrderStatus.CANCELLED,
            LabOrderStatus.FULLY_COMPLETED,
        ):
            self.status = LabOrderStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])
            return

        if self.status == LabOrderStatus.CANCELLED:
            return

        items = list(self.items.all())
        if not items:
            return

        statuses = {item.status for item in items}
        all_done = statuses <= {LabOrderItemStatus.COMPLETED, LabOrderItemStatus.CANCELLED}
        any_completed = LabOrderItemStatus.COMPLETED in statuses
        any_pending = LabOrderItemStatus.PENDING in statuses

        if all_done:
            self.status = LabOrderStatus.FULLY_COMPLETED
            self.fully_completed_at = now
            self.save(update_fields=["status", "fully_completed_at", "updated_at"])
        elif any_completed and any_pending:
            self.status = LabOrderStatus.PARTIALLY_COMPLETED
            self.save(update_fields=["status", "updated_at"])
        elif any_pending:
            self.status = LabOrderStatus.ISSUED
            self.save(update_fields=["status", "updated_at"])

    def clean(self):
        valid_statuses = {ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED}
        if self.consultation.status not in valid_statuses:
            raise ValidationError(
                "Lab order can only be created for accepted or doctor_responded consultations."
            )
        if self.doctor_id != self.consultation.assigned_doctor_id:
            raise ValidationError(
                "Only assigned doctor can create a lab order for this consultation."
            )
        if self.patient_id != self.consultation.patient_id:
            raise ValidationError("Patient must match the consultation patient.")
        if self.doctor.user_type != UserType.DOCTOR:
            raise ValidationError("Ordering user must be a doctor.")
        if self.patient.user_type != UserType.PATIENT:
            raise ValidationError("Lab order patient must be a patient user.")

        try:
            doctor_approved = (
                self.doctor.doctor_profile.verification_status == VerificationStatus.APPROVED
            )
        except Exception:
            doctor_approved = False
        if not doctor_approved:
            raise ValidationError("Doctor must be approved to create lab orders.")

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = _generate_unique_qr_token()
            self.qr_token_created_at = timezone.now()
        if not self.expires_at:
            self.expires_at = (self.qr_token_created_at or timezone.now()) + timedelta(
                days=LAB_ORDER_EXPIRY_DAYS
            )
        super().save(*args, **kwargs)


def _generate_unique_qr_token() -> str:
    for _ in range(10):
        token = secrets.token_urlsafe(32)
        if not LabOrder.objects.filter(qr_token=token).exists():
            return token
    raise RuntimeError("Could not generate a unique lab order QR token.")


class LabOrderItem(BaseModel):
    lab_order = models.ForeignKey(
        LabOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    test = models.ForeignKey(
        LabTestCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_order_items",
    )
    test_name = models.CharField(max_length=200)
    lab_test = models.ForeignKey(
        "lab_catalog.LabTest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_order_items",
    )
    custom_test_name = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=30, choices=LabTestCategory.choices)
    sample_type = models.CharField(max_length=100, blank=True)
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=LabOrderItemStatus.choices,
        default=LabOrderItemStatus.PENDING,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["lab_order", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.test_name} [{self.status}]"

    @property
    def display_test_name(self):
        if self.lab_test_id:
            try:
                return self.lab_test.display_name
            except Exception:
                pass
        if self.custom_test_name:
            return self.custom_test_name
        if self.test_name:
            return self.test_name
        return ""


class LabCompletionRecord(BaseModel):
    lab_order = models.ForeignKey(
        LabOrder,
        on_delete=models.CASCADE,
        related_name="completion_records",
    )
    lab_order_item = models.ForeignKey(
        LabOrderItem,
        on_delete=models.CASCADE,
        related_name="completion_records",
    )
    laboratorian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lab_completion_records",
    )
    status = models.CharField(max_length=20, choices=LabCompletionAttemptStatus.choices)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lab_order", "-created_at"]),
            models.Index(fields=["laboratorian", "-created_at"]),
        ]

    def __str__(self):
        return f"LabCompletionRecord {self.id} [{self.status}]"

    def clean(self):
        if self.laboratorian.user_type != UserType.LABORATORIAN:
            raise ValidationError("Only laboratorians can create completion records.")
        try:
            approved = (
                self.laboratorian.laboratorian_profile.verification_status
                == VerificationStatus.APPROVED
            )
        except Exception:
            approved = False
        if not approved:
            raise ValidationError("Laboratorian must be approved.")
        if self.lab_order.is_locked():
            raise ValidationError("Cannot complete tests for a locked lab order.")
        if self.lab_order_item.lab_order_id != self.lab_order_id:
            raise ValidationError("Lab order item does not belong to this lab order.")


class LabResult(BaseModel):
    lab_order = models.ForeignKey(
        LabOrder,
        on_delete=models.CASCADE,
        related_name="results",
    )
    lab_order_item = models.OneToOneField(
        LabOrderItem,
        on_delete=models.CASCADE,
        related_name="result",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lab_results",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ordered_lab_results",
    )
    laboratorian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_lab_results",
    )
    status = models.CharField(
        max_length=20,
        choices=LabResultStatus.choices,
        default=LabResultStatus.SUBMITTED,
    )
    value_type = models.CharField(max_length=30, choices=LabResultValueType.choices)
    text_value = models.TextField(blank=True)
    numeric_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    blood_group_value = models.CharField(max_length=20, choices=BloodGroup.choices, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    flag = models.CharField(
        max_length=20, choices=LabResultFlag.choices, default=LabResultFlag.UNKNOWN
    )
    result_file = models.FileField(upload_to=lab_result_file_upload_path, null=True, blank=True)
    original_file_name = models.CharField(max_length=255, blank=True)
    laboratorian_notes = models.TextField(blank=True)
    doctor_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    corrected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    is_linked_to_medical_record = models.BooleanField(default=False)
    linked_entry = models.ForeignKey(
        "patient_records.MedicalRecordEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_lab_results",
    )
    linked_blood_group_record = models.ForeignKey(
        "patient_records.BloodGroupRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_lab_results",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["doctor", "-created_at"]),
            models.Index(fields=["laboratorian", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["released_at"]),
        ]

    def __str__(self):
        return f"LabResult {self.id} [{self.status}]"

    def clean(self):
        if self.lab_order_item.lab_order_id != self.lab_order_id:
            raise ValidationError("Lab order item must belong to this lab order.")
        if self.patient_id != self.lab_order.patient_id:
            raise ValidationError("Patient must match the lab order patient.")
        if self.doctor_id != self.lab_order.doctor_id:
            raise ValidationError("Doctor must match the lab order doctor.")
        if self.laboratorian.user_type != UserType.LABORATORIAN:
            raise ValidationError("Result author must be a laboratorian.")
        try:
            approved = (
                self.laboratorian.laboratorian_profile.verification_status
                == VerificationStatus.APPROVED
            )
        except Exception:
            approved = False
        if not approved:
            raise ValidationError("Laboratorian must be approved.")

        if self.lab_order_item.status != LabOrderItemStatus.COMPLETED:
            raise ValidationError("Lab result can only be created for completed lab order items.")

        if self.value_type == LabResultValueType.NUMERIC and self.numeric_value is None:
            raise ValidationError({"numeric_value": "This field is required for numeric results."})
        if self.value_type == LabResultValueType.TEXT and not self.text_value:
            raise ValidationError({"text_value": "This field is required for text results."})
        if self.value_type == LabResultValueType.BLOOD_GROUP and not self.blood_group_value:
            raise ValidationError(
                {"blood_group_value": "This field is required for blood group results."}
            )
        if self.value_type == LabResultValueType.FILE_ONLY and not self.result_file:
            raise ValidationError({"result_file": "This field is required for file-only results."})
        if self.value_type == LabResultValueType.POSITIVE_NEGATIVE:
            if (self.text_value or "").strip().lower() not in {"positive", "negative"}:
                raise ValidationError({"text_value": "Value must be 'positive' or 'negative'."})


class LabResultCorrection(BaseModel):
    lab_result = models.ForeignKey(
        LabResult,
        on_delete=models.CASCADE,
        related_name="corrections",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lab_result_corrections",
    )
    previous_data = models.JSONField(default=dict, blank=True)
    new_data = models.JSONField(default=dict, blank=True)
    reason = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lab_result", "-created_at"]),
        ]

    def __str__(self):
        return f"LabResultCorrection {self.id}"
