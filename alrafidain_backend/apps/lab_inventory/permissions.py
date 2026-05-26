from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.policies import RoleAccessPolicy


class IsLabInventoryAccess(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        if RoleAccessPolicy.is_admin_or_staff(user):
            return True

        return RoleAccessPolicy.is_laboratorian(user)

    def has_object_permission(self, request, view, obj):
        user = request.user

        if RoleAccessPolicy.is_admin_or_staff(user):
            return True

        is_owner = RoleAccessPolicy.is_laboratorian(user) and obj.lab.user_id == user.id

        if request.method in SAFE_METHODS:
            if is_owner:
                return True
            return bool(obj.is_active and obj.is_available)

        return is_owner
