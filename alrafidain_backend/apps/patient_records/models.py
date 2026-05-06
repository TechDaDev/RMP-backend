from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.choices import (
    BloodGroup,
    MedicalRecordCategory,
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    UserType,
)
from apps.common.models import BaseModel


class PatientMedicalRecord(BaseModel):
    patient = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medical_record",
    )

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.patient and self.patient.user_type != UserType.PATIENT:
            raise ValidationError({"patient": "Medical record owner must be a patient."})

    def __str__(self):
        return f"Medical Record for {self.patient.email}"


class MedicalRecordEntry(BaseModel):
    medical_record = models.ForeignKey(
        PatientMedicalRecord,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    category = models.CharField(max_length=50, choices=MedicalRecordCategory.choices)
    title = models.CharField(max_length=255)
    value = models.TextField()
    verification_status = models.CharField(
        max_length=30,
        choices=MedicalRecordVerificationStatus.choices,
        default=MedicalRecordVerificationStatus.SELF_REPORTED,
    )
    source_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_medical_record_entries",
    )
    source_role = models.CharField(max_length=20, choices=MedicalRecordSourceRole.choices)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_medical_record_entries",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["medical_record", "is_active"]),
            models.Index(fields=["medical_record", "category"]),
            models.Index(fields=["verification_status"]),
            models.Index(fields=["medical_record", "is_active", "-created_at"]),
            models.Index(fields=["source_user", "-created_at"]),
            models.Index(fields=["verified_by", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.category} - {self.title}"


class BloodGroupRecord(BaseModel):
    medical_record = models.OneToOneField(
        PatientMedicalRecord,
        on_delete=models.CASCADE,
        related_name="blood_group_record",
    )
    blood_group = models.CharField(
        max_length=20,
        choices=BloodGroup.choices,
        default=BloodGroup.UNKNOWN,
    )
    verification_status = models.CharField(
        max_length=30,
        choices=MedicalRecordVerificationStatus.choices,
        default=MedicalRecordVerificationStatus.UNKNOWN,
    )
    source_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blood_group_sources",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blood_group_verifications",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Blood Group ({self.blood_group}) for {self.medical_record.patient.email}"
