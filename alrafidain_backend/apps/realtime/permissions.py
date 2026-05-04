"""
Permission checks for WebSocket consumers.
"""

from apps.consultations.models import Consultation


def can_connect_user_socket(user):
    """
    Check if user can connect to user-level WebSocket.

    Rules:
    - User must be authenticated

    Args:
        user: Django User instance

    Returns:
        bool: True if user can connect
    """
    return user.is_authenticated


async def can_connect_consultation_messages(user, consultation):
    """
    Check if user can connect to consultation messages WebSocket.

    Rules:
    - User must be authenticated
    - User must be consultation patient or assigned doctor
    - Consultation must be accepted, doctor_responded, or closed

    Args:
        user: Django User instance
        consultation: Consultation instance

    Returns:
        bool: True if user can connect
    """
    if not user.is_authenticated:
        return False

    # Check if consultation exists
    if not consultation:
        return False

    # Check if user is patient or assigned doctor
    is_patient = consultation.patient_id == user.id
    is_doctor = (
        consultation.assigned_doctor_id == user.id
        if consultation.assigned_doctor_id
        else False
    )

    if not (is_patient or is_doctor):
        return False

    # Check consultation status - must be accepted, doctor_responded, or closed for read-only
    allowed_statuses = ["accepted", "doctor_responded", "closed"]
    if consultation.status not in allowed_statuses:
        return False

    return True
