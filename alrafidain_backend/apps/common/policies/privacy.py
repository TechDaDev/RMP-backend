from apps.common.choices import LabResultStatus

from .role_access import RoleAccessPolicy


class PrivacyPolicy:
    @staticmethod
    def can_patient_see_prescription_items(user, prescription) -> bool:
        return bool(RoleAccessPolicy.is_patient(user) and prescription.patient_id == user.id)

    @staticmethod
    def can_patient_see_lab_order_items(user, lab_order) -> bool:
        return bool(RoleAccessPolicy.is_patient(user) and lab_order.patient_id == user.id)

    @staticmethod
    def can_patient_see_lab_result(user, lab_result) -> bool:
        return bool(
            RoleAccessPolicy.is_patient(user)
            and lab_result.patient_id == user.id
            and lab_result.status == LabResultStatus.RELEASED
        )

    @staticmethod
    def can_staff_see_internal_notes(user) -> bool:
        return RoleAccessPolicy.is_admin_or_staff(user)
