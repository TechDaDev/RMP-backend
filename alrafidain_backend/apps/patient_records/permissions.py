from apps.common.choices import UserType
from apps.common.policies import RoleAccessPolicy


def can_view_medical_report(user, report) -> bool:
    if not user or not user.is_authenticated:
        return False

    if report.patient_id == user.id:
        return True

    if RoleAccessPolicy.is_admin_or_staff(user):
        return True

    if user.user_type != UserType.DOCTOR:
        return False

    if not RoleAccessPolicy.is_verified_doctor(user):
        return False

    consultation = report.consultation
    if consultation is None:
        return False

    return consultation.assigned_doctor_id == user.id


def can_review_medical_report(user, report) -> bool:
    if not user or not user.is_authenticated:
        return False

    if RoleAccessPolicy.is_admin_or_staff(user):
        return True

    if user.user_type != UserType.DOCTOR:
        return False

    if not RoleAccessPolicy.is_verified_doctor(user):
        return False

    consultation = report.consultation
    if consultation is None:
        return False

    return consultation.assigned_doctor_id == user.id
