from apps.common.choices import UserType, VerificationStatus


def is_patient(user) -> bool:
    return bool(user and user.is_authenticated and user.user_type == UserType.PATIENT)


def is_approved_doctor(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.DOCTOR:
        return False
    try:
        return user.doctor_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def is_consultation_patient(user, consultation) -> bool:
    return bool(user and user.is_authenticated and consultation.patient_id == user.id)


def is_assigned_doctor(user, consultation) -> bool:
    return bool(user and user.is_authenticated and consultation.assigned_doctor_id == user.id)
