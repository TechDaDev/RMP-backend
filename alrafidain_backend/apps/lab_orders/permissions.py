from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy


def is_approved_doctor(user) -> bool:
    return RoleAccessPolicy.is_verified_doctor(user)


def is_approved_laboratorian(user) -> bool:
    return RoleAccessPolicy.is_verified_laboratorian(user)


def is_lab_order_patient(user, lab_order) -> bool:
    return bool(RoleAccessPolicy.is_patient(user) and lab_order.patient_id == user.id)


def is_lab_order_doctor(user, lab_order) -> bool:
    if not RoleAccessPolicy.is_doctor(user):
        return False
    return ClinicalAccessPolicy.can_user_access_lab_order(user, lab_order)
