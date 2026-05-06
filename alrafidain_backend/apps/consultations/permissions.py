from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy


def is_patient(user) -> bool:
    return RoleAccessPolicy.is_patient(user)


def is_approved_doctor(user) -> bool:
    return RoleAccessPolicy.is_verified_doctor(user)


def is_consultation_patient(user, consultation) -> bool:
    return bool(RoleAccessPolicy.is_patient(user) and consultation.patient_id == user.id)


def is_assigned_doctor(user, consultation) -> bool:
    if not RoleAccessPolicy.is_doctor(user):
        return False
    if not ClinicalAccessPolicy.can_user_access_consultation(user, consultation):
        return False
    return consultation.assigned_doctor_id == user.id
