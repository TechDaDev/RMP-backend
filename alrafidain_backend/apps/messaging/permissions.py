from apps.common.choices import ConsultationStatus, UserType
from apps.common.policies import ClinicalAccessPolicy

READABLE_STATUSES = [
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.DOCTOR_RESPONDED,
    ConsultationStatus.CLOSED,
]

SENDABLE_STATUSES = [
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.DOCTOR_RESPONDED,
]


def can_access_consultation_messages(user, consultation) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.user_type not in [UserType.PATIENT, UserType.DOCTOR]:
        return False
    return ClinicalAccessPolicy.can_user_access_consultation(user, consultation)


def can_read_messages(user, consultation) -> bool:
    if not can_access_consultation_messages(user, consultation):
        return False
    return consultation.status in READABLE_STATUSES


def can_send_messages(user, consultation) -> bool:
    if not can_access_consultation_messages(user, consultation):
        return False
    return consultation.status in SENDABLE_STATUSES
