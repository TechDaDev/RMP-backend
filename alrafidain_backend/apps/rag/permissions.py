"""
RAG permissions helpers.
"""

from apps.common.policies import RoleAccessPolicy


def is_approved_doctor(user) -> bool:
    """Return True if user is an authenticated, approved doctor."""
    return RoleAccessPolicy.is_verified_doctor(user)


def can_access_consultation_rag(user, consultation) -> bool:
    """Return True if the user is the assigned approved doctor for this consultation."""
    if not is_approved_doctor(user):
        return False
    return consultation.assigned_doctor_id == user.pk


def can_access_lab_result_rag(user, lab_result) -> bool:
    """Return True if the user is the ordering approved doctor for this lab result."""
    if not is_approved_doctor(user):
        return False
    return lab_result.doctor_id == user.pk
