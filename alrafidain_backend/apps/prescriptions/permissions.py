from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy


def is_approved_pharmacist(user) -> bool:
    return RoleAccessPolicy.is_verified_pharmacist(user)


def is_prescription_patient(user, prescription) -> bool:
    return bool(RoleAccessPolicy.is_patient(user) and prescription.patient_id == user.id)


def is_prescription_doctor(user, prescription) -> bool:
    if not RoleAccessPolicy.is_doctor(user):
        return False
    return ClinicalAccessPolicy.can_user_access_prescription(user, prescription)
