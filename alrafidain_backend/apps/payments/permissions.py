from rest_framework.permissions import BasePermission

from apps.common.policies import RoleAccessPolicy


class IsAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return RoleAccessPolicy.is_admin_or_staff(request.user)
