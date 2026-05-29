from rest_framework.permissions import BasePermission

from apps.common.policies import RoleAccessPolicy
from apps.common.choices import StaffRole
from apps.common.staff_access import has_staff_capability


def is_financial_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False

    try:
        staff_profile = user.staff_profile
    except Exception:
        return False

    return staff_profile.is_active and staff_profile.staff_role == StaffRole.FINANCIAL


def is_financial_or_admin(user) -> bool:
    return RoleAccessPolicy.is_admin_or_staff(user) or is_financial_user(user)


class IsAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return is_financial_or_admin(request.user)


class IsFinancialOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_financial_or_admin(request.user)


def is_finance_reviewer(user) -> bool:
    return has_staff_capability(user, "manage_finance")


class IsFinanceReviewer(BasePermission):
    def has_permission(self, request, view):
        return is_finance_reviewer(request.user)
