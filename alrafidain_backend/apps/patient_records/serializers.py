from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.choices import MedicalRecordVerificationStatus

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord

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
        active_entries = obj.entries.filter(is_active=True).order_by("-created_at")
        return MedicalRecordEntrySerializer(active_entries, many=True).data
