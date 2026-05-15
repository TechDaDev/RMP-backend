from contextlib import suppress

from django.conf import settings
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.common.choices import MedicalSpecialty
from apps.common.file_validation import validate_uploaded_file

from .models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    StaffProfile,
    UserProfile,
)

_VERIFICATION_READ_ONLY = ["verification_status", "verified_at", "verification_notes"]


class UserProfileSerializer(serializers.ModelSerializer):
    def validate_profile_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "phone_number",
            "profile_image",
            "gender",
            "date_of_birth",
            "governorate",
            "district",
            "address",
            "national_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PatientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "social_security_id",
            "emergency_contact_name",
            "emergency_contact_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DoctorProfileSerializer(serializers.ModelSerializer):
    def validate_medical_license_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    def validate(self, attrs):
        specialty = attrs.get("specialty", getattr(self.instance, "specialty", ""))
        specialty_other = attrs.get(
            "specialty_other", getattr(self.instance, "specialty_other", "")
        )
        if specialty == MedicalSpecialty.OTHER and not specialty_other:
            raise serializers.ValidationError(
                {"specialty_other": "This field is required when specialty is Other."}
            )
        if specialty != MedicalSpecialty.OTHER and "specialty_other" in attrs:
            attrs["specialty_other"] = ""
        return attrs

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "medical_license_number",
            "medical_license_image",
            "specialty",
            "specialty_other",
            "subspecialty",
            "professional_title",
            "years_of_experience",
            "bio",
            "work_address",
            "verification_status",
            "verified_at",
            "verification_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"] + _VERIFICATION_READ_ONLY


class PharmacistProfileSerializer(serializers.ModelSerializer):
    def validate_pharmacist_license_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    def validate_pharmacy_license_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    class Meta:
        model = PharmacistProfile
        fields = [
            "id",
            "pharmacist_license_number",
            "pharmacist_license_image",
            "pharmacy_name",
            "pharmacy_license_number",
            "pharmacy_license_image",
            "pharmacy_address",
            "working_hours",
            "verification_status",
            "verified_at",
            "verification_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"] + _VERIFICATION_READ_ONLY


class LaboratorianProfileSerializer(serializers.ModelSerializer):
    def validate_laboratorian_license_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    def validate_laboratory_license_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.PROFILE_IMAGE_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.PROFILE_IMAGE_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_PROFILE_IMAGE_UPLOAD_MB,
        )
        return value

    class Meta:
        model = LaboratorianProfile
        fields = [
            "id",
            "laboratorian_license_number",
            "laboratorian_license_image",
            "laboratory_name",
            "laboratory_license_number",
            "laboratory_license_image",
            "laboratory_address",
            "specialization",
            "working_hours",
            "verification_status",
            "verified_at",
            "verification_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"] + _VERIFICATION_READ_ONLY


class FullProfileSerializer(serializers.Serializer):
    def to_representation(self, instance):
        from apps.common.choices import UserType, VerificationStatus

        from .staff_serializers import StaffDetailSerializer

        user = instance
        user_profile_obj = None
        role_profile_obj = None
        role_serializer = None
        role_profile_data = None

        with suppress(UserProfile.DoesNotExist):
            user_profile_obj = user.user_profile

        user_type = user.user_type

        if user_type == UserType.PATIENT:
            try:
                role_profile_obj = user.patient_profile
                role_serializer = PatientProfileSerializer
            except PatientProfile.DoesNotExist:
                pass
        elif user_type == UserType.DOCTOR:
            try:
                role_profile_obj = user.doctor_profile
                role_serializer = DoctorProfileSerializer
            except DoctorProfile.DoesNotExist:
                pass
        elif user_type == UserType.PHARMACIST:
            try:
                role_profile_obj = user.pharmacist_profile
                role_serializer = PharmacistProfileSerializer
            except PharmacistProfile.DoesNotExist:
                pass
        elif user_type == UserType.LABORATORIAN:
            try:
                role_profile_obj = user.laboratorian_profile
                role_serializer = LaboratorianProfileSerializer
            except LaboratorianProfile.DoesNotExist:
                pass
        elif user_type == UserType.STAFF:
            try:
                role_profile_obj = user.staff_profile
                role_serializer = StaffDetailSerializer
            except StaffProfile.DoesNotExist:
                pass

        if role_profile_obj is not None and role_serializer is not None:
            role_profile_data = role_serializer(role_profile_obj).data

        # — Completion —
        shared_complete = user_profile_obj.is_complete if user_profile_obj else False
        shared_missing = user_profile_obj.missing_fields if user_profile_obj else []
        if role_profile_obj is not None and hasattr(role_profile_obj, "is_complete"):
            role_complete = role_profile_obj.is_complete
        else:
            # Staff profiles are not tracked with role completeness fields.
            role_complete = role_profile_obj is not None

        if role_profile_obj is not None and hasattr(role_profile_obj, "missing_fields"):
            role_missing = role_profile_obj.missing_fields
        else:
            role_missing = []

        completion = {
            "shared_profile_complete": shared_complete,
            "role_profile_complete": role_complete,
            "overall_complete": shared_complete and role_complete,
            "missing_shared_fields": shared_missing,
            "missing_role_fields": role_missing,
        }

        # — Verification —
        professional_types = {UserType.DOCTOR, UserType.PHARMACIST, UserType.LABORATORIAN}
        if user_type in professional_types and role_profile_obj is not None:
            v_status = role_profile_obj.verification_status
            verification = {
                "required": True,
                "status": v_status,
                "is_approved": v_status == VerificationStatus.APPROVED,
            }
        else:
            verification = {
                "required": False,
                "status": None,
                "is_approved": None,
            }

        return {
            "user": UserSerializer(user).data,
            "user_profile": UserProfileSerializer(user_profile_obj).data
            if user_profile_obj
            else None,
            "role_profile": role_profile_data,
            "completion": completion,
            "verification": verification,
        }
