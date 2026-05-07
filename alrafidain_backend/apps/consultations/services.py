import logging
from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.services import create_audit_log
from apps.common.choices import ConsultationStatus, MedicalSpecialty, NotificationType
from apps.notifications.services import create_notification

from .models import Symptom, SymptomSpecialtyRule

logger = logging.getLogger(__name__)


def infer_specialty_from_symptoms(symptoms) -> str:
    active_symptoms = [symptom for symptom in symptoms if symptom.is_active]
    active_ids = [symptom.id for symptom in active_symptoms]

    scores = defaultdict(int)
    rules = SymptomSpecialtyRule.objects.filter(symptom_id__in=active_ids, is_active=True)
    for rule in rules:
        scores[rule.specialty] += rule.weight

    if scores:
        # TODO: Replace deterministic routing with AI-assisted triage once backend AI triage exists.
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]

    specialty_values = {value for value, _label in MedicalSpecialty.choices}
    if MedicalSpecialty.GENERAL_MEDICINE in specialty_values:
        return MedicalSpecialty.GENERAL_MEDICINE

    raise serializers.ValidationError(
        {"symptom_ids": "Unable to infer consultation specialty from the selected symptoms."}
    )


def recommend_specialty_from_symptoms(symptom_ids):
    symptoms = Symptom.objects.filter(id__in=symptom_ids, is_active=True).select_related("category")
    active_ids = [s.id for s in symptoms]

    scores = defaultdict(int)
    rules = SymptomSpecialtyRule.objects.filter(symptom_id__in=active_ids, is_active=True)
    for rule in rules:
        scores[rule.specialty] += rule.weight

    has_red_flag = any(symptom.is_red_flag for symptom in symptoms)
    recommended_specialty = infer_specialty_from_symptoms(symptoms)
    return {
        "recommended_specialty": recommended_specialty,
        "scores": dict(scores),
        "has_red_flag": has_red_flag,
    }


@transaction.atomic
def accept_consultation(*, consultation, doctor, request=None):
    consultation.assigned_doctor = doctor
    consultation.status = ConsultationStatus.ACCEPTED
    consultation.accepted_at = timezone.now()
    consultation.save(update_fields=["assigned_doctor", "status", "accepted_at", "updated_at"])

    create_audit_log(
        actor=doctor,
        action="consultation_accepted",
        target=consultation,
        request=request,
    )
    create_notification(
        recipient=consultation.patient,
        notification_type=NotificationType.CONSULTATION,
        title="Consultation accepted",
        message="A doctor has accepted your consultation.",
        data={
            "consultation_id": str(consultation.id),
            "doctor_id": str(doctor.id),
            "status": ConsultationStatus.ACCEPTED,
        },
    )

    def broadcast_update():
        from apps.realtime.services import broadcast_consultation_updated

        try:
            broadcast_consultation_updated(consultation)
        except Exception as exc:
            logger.error("Failed to broadcast consultation.updated event: %s", exc)

    transaction.on_commit(broadcast_update)
    return consultation


@transaction.atomic
def add_consultation_response(
    *, consultation, doctor, response_text, recommendation_type, request=None
):
    from .models import ConsultationResponse

    response = ConsultationResponse.objects.create(
        consultation=consultation,
        doctor=doctor,
        response_text=response_text,
        recommendation_type=recommendation_type,
    )

    consultation.status = ConsultationStatus.DOCTOR_RESPONDED
    consultation.save(update_fields=["status", "updated_at"])

    create_audit_log(
        actor=doctor,
        action="consultation_response_created",
        target=consultation,
        metadata={"response_id": str(response.id)},
        request=request,
    )
    create_notification(
        recipient=consultation.patient,
        notification_type=NotificationType.CONSULTATION,
        title="Doctor response added",
        message="Your doctor has added a response to your consultation.",
        data={
            "consultation_id": str(consultation.id),
            "status": ConsultationStatus.DOCTOR_RESPONDED,
        },
    )

    def broadcast_update():
        from apps.realtime.services import broadcast_consultation_updated

        try:
            consultation.refresh_from_db()
            broadcast_consultation_updated(consultation)
        except Exception as exc:
            logger.error("Failed to broadcast consultation.updated event: %s", exc)

    transaction.on_commit(broadcast_update)
    return response


@transaction.atomic
def close_consultation(*, consultation, doctor, request=None):
    consultation.status = ConsultationStatus.CLOSED
    consultation.closed_at = timezone.now()
    consultation.save(update_fields=["status", "closed_at", "updated_at"])

    create_audit_log(
        actor=doctor,
        action="consultation_closed",
        target=consultation,
        request=request,
    )
    create_notification(
        recipient=consultation.patient,
        notification_type=NotificationType.CONSULTATION,
        title="Consultation closed",
        message="Your consultation has been closed.",
        data={"consultation_id": str(consultation.id), "status": ConsultationStatus.CLOSED},
    )

    def broadcast_update():
        from apps.realtime.services import broadcast_consultation_updated

        try:
            broadcast_consultation_updated(consultation)
        except Exception as exc:
            logger.error("Failed to broadcast consultation.updated event: %s", exc)

    transaction.on_commit(broadcast_update)
    return consultation
