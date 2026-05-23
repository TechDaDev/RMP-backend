from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.choices import (
    BloodGroup,
    MedicalRecordCategory,
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    MedicalReportProcessingStatus,
    MedicalReportSource,
    MedicalReportType,
    MedicalReportVisibility,
    UserType,
)
from apps.common.models import BaseModel
from apps.common.upload_paths import medical_report_upload_path


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


class PatientMedicalReport(BaseModel):
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medical_reports",
    )
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_reports",
    )
    source_message = models.ForeignKey(
        "messaging.ConsultationMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_reports",
    )
    source_attachment = models.ForeignKey(
        "messaging.MessageAttachment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_reports",
    )
    linked_medical_record_entry = models.ForeignKey(
        "MedicalRecordEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_medical_reports",
    )
    source = models.CharField(
        max_length=40,
        choices=MedicalReportSource.choices,
        default=MedicalReportSource.CHAT_ATTACHMENT,
    )
    report_type = models.CharField(
        max_length=40,
        choices=MedicalReportType.choices,
        default=MedicalReportType.UNKNOWN,
    )
    processing_status = models.CharField(
        max_length=40,
        choices=MedicalReportProcessingStatus.choices,
        default=MedicalReportProcessingStatus.UPLOADED,
    )
    visibility = models.CharField(
        max_length=50,
        choices=MedicalReportVisibility.choices,
        default=MedicalReportVisibility.PATIENT_AND_ASSIGNED_DOCTOR,
    )
    title = models.CharField(max_length=255)
    original_file = models.FileField(
        upload_to=medical_report_upload_path,
        null=True,
        blank=True,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    raw_ocr_text = models.TextField(blank=True)
    cleaned_report_text = models.TextField(blank=True)
    structured_payload = models.JSONField(default=dict, blank=True)
    removed_noise_summary = models.JSONField(default=list, blank=True)
    detected_language = models.CharField(max_length=50, blank=True)
    llm_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
    )
    is_medical_report = models.BooleanField(default=False)
    rejection_reason = models.CharField(max_length=120, blank=True)
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_medical_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    doctor_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["consultation", "-created_at"]),
            models.Index(fields=["source_attachment"]),
            models.Index(fields=["report_type"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["is_medical_report"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_attachment"],
                condition=models.Q(source_attachment__isnull=False),
                name="uniq_medical_report_source_attachment",
            )
        ]

    def clean(self):
        if self.patient and self.patient.user_type != UserType.PATIENT:
            raise ValidationError({"patient": "Medical report owner must be a patient."})

        if self.consultation and self.consultation.patient_id != self.patient_id:
            raise ValidationError(
                {"consultation": "Consultation patient must match report patient."}
            )

        if (
            self.source_message
            and self.consultation
            and self.source_message.consultation_id != self.consultation_id
        ):
            raise ValidationError(
                {"source_message": "Source message must belong to the selected consultation."}
            )

        if self.source_attachment:
            attachment_message_id = self.source_attachment.message_id
            if self.source_message and attachment_message_id != self.source_message_id:
                raise ValidationError(
                    {"source_attachment": "Source attachment must belong to source message."}
                )

            message = self.source_attachment.message
            if self.source_message and self.source_attachment.uploaded_by_id != message.sender_id:
                raise ValidationError(
                    {"source_attachment": "Attachment uploader must match message sender."}
                )

            consultation = message.consultation
            if consultation.patient_id != self.patient_id:
                raise ValidationError(
                    {"source_attachment": "Source attachment does not belong to this patient."}
                )

        if self.report_type == MedicalReportType.NOT_MEDICAL_REPORT:
            self.is_medical_report = False

        if not self.is_medical_report and self.report_type not in {
            MedicalReportType.UNKNOWN,
            MedicalReportType.NOT_MEDICAL_REPORT,
        }:
            raise ValidationError(
                {
                    "report_type": (
                        "Non-medical reports must use unknown or not_medical_report type."
                    )
                }
            )

    def __str__(self):
        return f"{self.report_type} report for {self.patient.email}"
