from rest_framework import serializers

from .models import DoctorProfile, LaboratorianProfile, PharmacistProfile


def _resolve_phone_number(user):
    try:
        return user.user_profile.phone_number
    except Exception:
        return ""


class AdminVerificationUserSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()
    date_joined = serializers.DateTimeField()


class AdminVerificationProfileSummarySerializer(serializers.Serializer):
    def to_representation(self, instance):
        role = instance["role"]
        profile = instance["profile"]

        if role == "doctor":
            return {
                "license_number": profile.medical_license_number,
                "specialty": profile.specialty,
                "workplace_name": profile.professional_title,
                "address": profile.work_address,
                "years_of_experience": profile.years_of_experience,
                "phone_number": _resolve_phone_number(profile.user),
            }

        if role == "pharmacist":
            return {
                "license_number": profile.pharmacist_license_number,
                "pharmacy_name": profile.pharmacy_name,
                "pharmacy_address": profile.pharmacy_address,
                "phone_number": _resolve_phone_number(profile.user),
            }

        return {
            "license_number": profile.laboratorian_license_number,
            "laboratory_name": profile.laboratory_name,
            "laboratory_address": profile.laboratory_address,
            "specialization": profile.specialization,
            "phone_number": _resolve_phone_number(profile.user),
        }


class AdminVerificationListSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    role = serializers.CharField()
    status = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    def get_id(self, obj):
        return obj["profile"].id

    def get_status(self, obj):
        return obj["profile"].verification_status

    def get_user(self, obj):
        user = obj["profile"].user
        return AdminVerificationUserSummarySerializer(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "date_joined": user.date_joined,
            }
        ).data

    def get_profile(self, obj):
        return AdminVerificationProfileSummarySerializer(obj).data

    def get_submitted_at(self, obj):
        return obj["profile"].created_at

    def get_updated_at(self, obj):
        return obj["profile"].updated_at


class AdminVerificationDetailSerializer(AdminVerificationListSerializer):
    verification_notes = serializers.SerializerMethodField()
    verified_at = serializers.SerializerMethodField()
    verified_by = serializers.SerializerMethodField()

    def get_verification_notes(self, obj):
        return obj["profile"].verification_notes

    def get_verified_at(self, obj):
        return obj["profile"].verified_at

    def get_verified_by(self, obj):
        reviewer = obj["profile"].verified_by
        if reviewer is None:
            return None
        return {
            "id": reviewer.id,
            "email": reviewer.email,
            "full_name": reviewer.full_name,
        }


class AdminVerificationDecisionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        action = self.context.get("action")
        if action in {"reject", "suspend"} and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": "This field is required."})
        return attrs


ROLE_PROFILE_MODEL_MAP = {
    "doctor": DoctorProfile,
    "pharmacist": PharmacistProfile,
    "laboratorian": LaboratorianProfile,
}
