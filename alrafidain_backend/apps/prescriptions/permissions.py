from apps.common.choices import UserType, VerificationStatus


def is_approved_pharmacist(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.PHARMACIST:
        return False
    try:
        return user.pharmacist_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def is_prescription_patient(user, prescription) -> bool:
    return bool(user and user.is_authenticated and prescription.patient_id == user.id)


def is_prescription_doctor(user, prescription) -> bool:
    return bool(user and user.is_authenticated and prescription.doctor_id == user.id)
