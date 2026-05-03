from apps.common.choices import UserType, VerificationStatus


def is_approved_doctor(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.DOCTOR:
        return False
    try:
        return user.doctor_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def is_approved_laboratorian(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.LABORATORIAN:
        return False
    try:
        return user.laboratorian_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def is_lab_order_patient(user, lab_order) -> bool:
    return bool(user and user.is_authenticated and lab_order.patient_id == user.id)


def is_lab_order_doctor(user, lab_order) -> bool:
    return bool(user and user.is_authenticated and lab_order.doctor_id == user.id)
