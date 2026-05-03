from rest_framework.permissions import BasePermission


class IsStaffOrSuperuser(BasePermission):
    """
    Allows access only to users who are staff members or superusers.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
