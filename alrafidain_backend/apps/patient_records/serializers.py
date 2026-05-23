from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.choices import (
    MedicalRecordVerificationStatus,
    MedicalReportProcessingStatus,
    MedicalReportType,
    UserType,
)
from apps.common.policies import RoleAccessPolicy

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord, PatientMedicalReport

User = get_user_model()


class UserSafeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]
        read_only_fields = fields


class BloodGroupRecordSerializer(serializers.ModelSerializer):
    source_user = UserSafeSummarySerializer(read_only=True)
    verified_by = UserSafeSummarySerializer(read_only=True)

    class Meta:
        model = BloodGroupRecord
        fields = [
            "id",
            "blood_group",
            "verification_status",
            "source_user",
            "verified_by",
            "verified_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MedicalRecordEntrySerializer(serializers.ModelSerializer):
    source_user = UserSafeSummarySerializer(read_only=True)
    verified_by = UserSafeSummarySerializer(read_only=True)

    class Meta:
        model = MedicalRecordEntry
        fields = [
            "id",
            "category",
            "title",
            "value",
            "verification_status",
            "source_user",
            "source_role",
            "verified_by",
            "verified_at",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MedicalRecordEntryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecordEntry
        fields = ["category", "title", "value", "notes"]


class MedicalRecordEntryConfirmSerializer(serializers.Serializer):
    verification_status = serializers.ChoiceField(
        choices=[
            MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
            MedicalRecordVerificationStatus.REJECTED,
        ]
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class MedicalRecordEntryDeactivateSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)


class SetBloodGroupSerializer(serializers.Serializer):
    blood_group = serializers.ChoiceField(
        choices=BloodGroupRecord._meta.get_field("blood_group").choices
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class MessageAttachmentSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    original_name = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj):
        if not getattr(obj, "file", None):
            return ""

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)

        url = obj.file.url
        if url and not url.startswith("/"):
            return f"/{url}"
        return url


class ConsultationMessageSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    sender_role = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class MedicalRecordEntrySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecordEntry
        fields = ["id", "category", "title", "verification_status"]
        read_only_fields = fields


class PatientMedicalReportListSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()

    class Meta:
        model = PatientMedicalReport
        fields = [
            "id",
            "patient",
            "consultation",
            "source",
            "report_type",
            "processing_status",
            "visibility",
            "title",
            "original_filename",
            "is_medical_report",
            "detected_language",
            "llm_confidence",
            "rejection_reason",
            "created_at",
            "updated_at",
            "processed_at",
            "reviewed_at",
        ]
        read_only_fields = fields

    def get_patient(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and (user.user_type == UserType.DOCTOR or RoleAccessPolicy.is_admin_or_staff(user)):
            return {
                "id": str(obj.patient_id),
                "email": obj.patient.email,
            }
        return None


class PatientMedicalReportDetailSerializer(PatientMedicalReportListSerializer):
    linked_medical_record_entry = MedicalRecordEntrySummarySerializer(read_only=True)
    source_message = ConsultationMessageSummarySerializer(read_only=True)
    source_attachment = MessageAttachmentSummarySerializer(read_only=True)

    class Meta(PatientMedicalReportListSerializer.Meta):
        fields = PatientMedicalReportListSerializer.Meta.fields + [
            "raw_ocr_text",
            "cleaned_report_text",
            "structured_payload",
            "removed_noise_summary",
            "doctor_notes",
            "linked_medical_record_entry",
            "source_message",
            "source_attachment",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user and user.user_type == UserType.PATIENT:
            data.pop("raw_ocr_text", None)
            data.pop("patient", None)

        return data


class PatientMedicalReportDoctorReviewSerializer(serializers.Serializer):
    doctor_notes = serializers.CharField(required=False, allow_blank=True)
    mark_reviewed = serializers.BooleanField(required=False, default=True)
    report_type = serializers.ChoiceField(
        choices=MedicalReportType.choices,
        required=False,
    )
    is_medical_report = serializers.BooleanField(required=False)
    processing_status = serializers.ChoiceField(
        choices=MedicalReportProcessingStatus.choices,
        required=False,
    )


class PatientMedicalRecordSerializer(serializers.ModelSerializer):
    patient = UserSafeSummarySerializer(read_only=True)
    blood_group = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()

    class Meta:
        model = PatientMedicalRecord
        fields = ["id", "patient", "blood_group", "entries", "created_at", "updated_at"]
        read_only_fields = fields

    def get_blood_group(self, obj):
        blood_group_record = getattr(obj, "blood_group_record", None)
        if not blood_group_record:
            return None
        return BloodGroupRecordSerializer(blood_group_record).data

    def get_entries(self, obj):
        active_entries = getattr(obj, "active_entries", None)
        if active_entries is None:
            active_entries = (
                obj.entries.filter(is_active=True)
                .select_related("source_user", "verified_by")
                .order_by("-created_at")
            )
        return MedicalRecordEntrySerializer(active_entries, many=True).data
