import logging
import json
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.services import create_audit_log
from apps.common.choices import ConsultationStatus, MedicalSpecialty, NotificationType
from apps.notifications.services import create_notification

from .models import Symptom, SymptomSpecialtyRule

logger = logging.getLogger(__name__)


def _get_triage_max_specialties():
    configured_limit = getattr(settings, "CONSULTATION_TRIAGE_MAX_SPECIALTIES", 3)
    return max(1, min(configured_limit, 3))


def _allowed_specialty_values():
    return {value for value, _label in MedicalSpecialty.choices}


def _sorted_specialties_from_scores(scores, limit=None):
    ranked_specialties = [
        specialty
        for specialty, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
    if ranked_specialties:
        return ranked_specialties[:limit] if limit else ranked_specialties
    return [MedicalSpecialty.GENERAL_MEDICINE]


def _normalize_specialties(specialties, fallback_specialties, max_specialties):
    allowed_specialties = _allowed_specialty_values()
    normalized_specialties = []

    for specialty in specialties or []:
        if not isinstance(specialty, str):
            continue

        normalized_specialty = specialty.strip().lower()
        if (
            normalized_specialty in allowed_specialties
            and normalized_specialty not in normalized_specialties
        ):
            normalized_specialties.append(normalized_specialty)

    for specialty in fallback_specialties:
        if specialty not in normalized_specialties:
            normalized_specialties.append(specialty)

    return normalized_specialties[:max_specialties]


def _parse_llm_specialties(content):
    normalized_content = content.strip()
    if normalized_content.startswith("```"):
        lines = normalized_content.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized_content = "\n".join(lines).strip()

    candidates = [normalized_content]
    json_start = normalized_content.find("{")
    json_end = normalized_content.rfind("}")
    if json_start != -1 and json_end > json_start:
        candidates.append(normalized_content[json_start : json_end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        specialties = payload.get("specialties")
        if isinstance(specialties, list):
            return specialties

    raise ValueError("DeepSeek triage response did not contain a valid specialties list.")


def _build_triage_messages(symptoms, fallback_specialties, max_specialties):
    allowed_specialties = sorted(_allowed_specialty_values())
    symptom_lines = []
    for symptom in symptoms:
        category_name = getattr(symptom.category, "name", "Unknown")
        red_flag_label = "yes" if symptom.is_red_flag else "no"
        symptom_lines.append(
            f"- {symptom.name} | category: {category_name} | red_flag: {red_flag_label}"
        )

    fallback_text = ", ".join(fallback_specialties)
    allowed_text = ", ".join(allowed_specialties)

    return [
        {
            "role": "system",
            "content": (
                "You are a medical triage assistant for doctor specialty routing. "
                "Return strict JSON only with a 'specialties' array containing up to "
                f"{max_specialties} specialty values from the allowed list."
            ),
        },
        {
            "role": "user",
            "content": (
                "Choose the most relevant doctor specialties for these symptoms. "
                "Use only exact specialty values from the allowed list. Prefer higher-signal "
                "specialties first, and do not include explanations outside JSON.\n\n"
                f"Allowed specialties: {allowed_text}\n"
                f"Maximum specialties: {max_specialties}\n"
                f"Weighted fallback ranking: {fallback_text}\n"
                "Symptoms:\n"
                f"{"\n".join(symptom_lines)}\n\n"
                "Respond as JSON like: {\"specialties\": [\"cardiology\", \"internal_medicine\"]}"
            ),
        },
    ]


def _get_deepseek_client():
    from apps.rag.llm_clients.deepseek_client import get_default_deepseek_client

    return get_default_deepseek_client()


def _recommend_specialties_with_llm(symptoms, fallback_specialties, max_specialties):
    client = _get_deepseek_client()
    response = client.chat(
        _build_triage_messages(symptoms, fallback_specialties, max_specialties),
        temperature=0.1,
        max_tokens=250,
    )
    llm_specialties = _parse_llm_specialties(response["content"])
    return {
        "specialties": _normalize_specialties(llm_specialties, fallback_specialties, max_specialties),
        "usage": response.get("usage", {}),
    }


def infer_specialty_from_symptoms(symptoms) -> str:
    active_symptoms = [symptom for symptom in symptoms if symptom.is_active]
    active_ids = [symptom.id for symptom in active_symptoms]

    scores = defaultdict(int)
    rules = SymptomSpecialtyRule.objects.filter(symptom_id__in=active_ids, is_active=True)
    for rule in rules:
        scores[rule.specialty] += rule.weight

    ranked_specialties = _sorted_specialties_from_scores(scores, limit=1)
    if ranked_specialties:
        return ranked_specialties[0]

    raise serializers.ValidationError(
        {"symptom_ids": "Unable to infer consultation specialty from the selected symptoms."}
    )


def recommend_specialty_from_symptoms(symptom_ids):
    symptoms = list(
        Symptom.objects.filter(id__in=symptom_ids, is_active=True).select_related("category")
    )
    active_ids = [s.id for s in symptoms]

    scores = defaultdict(int)
    rules = SymptomSpecialtyRule.objects.filter(symptom_id__in=active_ids, is_active=True)
    for rule in rules:
        scores[rule.specialty] += rule.weight

    has_red_flag = any(symptom.is_red_flag for symptom in symptoms)
    fallback_specialties = _sorted_specialties_from_scores(
        scores,
        limit=_get_triage_max_specialties(),
    )

    recommended_specialties = fallback_specialties
    routing_method = "fallback"

    if getattr(settings, "CONSULTATION_TRIAGE_USE_LLM", True):
        try:
            llm_result = _recommend_specialties_with_llm(
                symptoms,
                fallback_specialties,
                _get_triage_max_specialties(),
            )
            recommended_specialties = llm_result["specialties"]
            routing_method = "llm"
            llm_usage = llm_result["usage"]
        except ModuleNotFoundError as exc:
            logger.warning("DeepSeek triage unavailable in this environment: %s", exc)
            llm_usage = {}
        except Exception as exc:
            logger.warning("DeepSeek triage fallback engaged: %s", exc)
            llm_usage = {}
    else:
        llm_usage = {}

    recommended_specialty = recommended_specialties[0]
    return {
        "recommended_specialty": recommended_specialty,
        "recommended_specialties": recommended_specialties,
        "scores": dict(scores),
        "has_red_flag": has_red_flag,
        "routing_method": routing_method,
        "llm_usage": llm_usage,
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

    transaction.on_commit(broadcast_update, robust=True)
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

    transaction.on_commit(broadcast_update, robust=True)
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

    transaction.on_commit(broadcast_update, robust=True)
    return consultation
