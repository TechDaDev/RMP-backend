from rest_framework.permissions import BasePermission


class IsAdminUserTypeOrStaff(BasePermission):
    """Allow access only to staff/superusers or explicit admin user_type."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return bool(
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or getattr(user, "user_type", "") == "admin"
        )
