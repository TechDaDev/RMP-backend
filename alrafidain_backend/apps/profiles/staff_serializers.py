"""
Serializers for staff profile endpoints.
"""

from rest_framework import serializers

from apps.common.staff_access import get_allowed_admin_sections

from .models import StaffProfile


class StaffListSerializer(serializers.ModelSerializer):
    """Minimal staff info for list views."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    role_display = serializers.CharField(source="get_staff_role_display", read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "user_email",
            "user_full_name",
            "staff_role",
            "role_display",
            "department",
            "is_active",
            "last_active",
        ]
        read_only_fields = ["id", "user_email", "user_full_name", "last_active"]


class StaffDetailSerializer(serializers.ModelSerializer):
    """Full staff profile detail."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    supervisor_email = serializers.CharField(
        source="supervisor.email", read_only=True, allow_null=True
    )
    role_display = serializers.CharField(source="get_staff_role_display", read_only=True)
    allowed_admin_sections = serializers.SerializerMethodField()

    def get_allowed_admin_sections(self, obj):
        return get_allowed_admin_sections(obj.user)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "user_email",
            "user_full_name",
            "staff_role",
            "role_display",
            "department",
            "supervisor_email",
            "can_approve_professionals",
            "can_manage_knowledge_base",
            "can_export_datasets",
            "can_view_audit_logs",
            "allowed_admin_sections",
            "hire_date",
            "last_active",
            "is_active",
            "has_completed_training",
            "training_completed_date",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user_email",
            "user_full_name",
            "supervisor_email",
            "hire_date",
            "last_active",
            "created_at",
        ]


class UserStaffProfileSerializer(serializers.Serializer):
    """Serializer for authenticated user's own staff profile (GET /api/profiles/me/staff/)."""

    id = serializers.UUIDField(source="staff_profile.id", read_only=True)
    staff_role = serializers.CharField(source="staff_profile.staff_role", read_only=True)
    role_display = serializers.CharField(
        source="staff_profile.get_staff_role_display", read_only=True
    )
    department = serializers.CharField(source="staff_profile.department", read_only=True)
    can_approve_professionals = serializers.BooleanField(
        source="staff_profile.can_approve_professionals", read_only=True
    )
    can_manage_knowledge_base = serializers.BooleanField(
        source="staff_profile.can_manage_knowledge_base", read_only=True
    )
    can_export_datasets = serializers.BooleanField(
        source="staff_profile.can_export_datasets", read_only=True
    )
    can_view_audit_logs = serializers.BooleanField(
        source="staff_profile.can_view_audit_logs", read_only=True
    )
    hire_date = serializers.DateField(source="staff_profile.hire_date", read_only=True)
    has_completed_training = serializers.BooleanField(
        source="staff_profile.has_completed_training", read_only=True
    )
    allowed_admin_sections = serializers.SerializerMethodField()

    def get_allowed_admin_sections(self, obj):
        if not hasattr(obj, "staff_profile"):
            return []
        return get_allowed_admin_sections(obj)

    def to_representation(self, instance):
        if not hasattr(instance, "staff_profile"):
            return None
        return super().to_representation(instance)
