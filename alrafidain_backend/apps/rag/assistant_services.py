from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    DoctorAIAssistantMessageStatus,
    DoctorAIAssistantSafetyLevel,
    DoctorAIAssistantTriggerType,
    NotificationType,
    RAGResponseStatus,
    RAGServiceContext,
)
from apps.notifications.services import create_notification

from .models import DoctorAIAssistantMessage
from .services import run_medical_report_case_update_rag

logger = logging.getLogger(__name__)


def _safe_document_titles(rag_response) -> list[str]:
    safety = (rag_response.raw_response or {}).get("safety", {})
    titles = safety.get("document_titles")
    if not isinstance(titles, list):
        return []
    return [str(x)[:255] for x in titles[:10] if x]


def _determine_safety_level(rag_response) -> str:
    if rag_response.status == RAGResponseStatus.NO_CONTEXT:
        return DoctorAIAssistantSafetyLevel.NO_CONTEXT
    if rag_response.status == RAGResponseStatus.FAILED:
        return DoctorAIAssistantSafetyLevel.FAILED

    confidence = ((rag_response.raw_response or {}).get("safety", {}) or {}).get("confidence")
    if confidence is not None:
        try:
            min_confidence = float(getattr(settings, "RAG_MIN_CONFIDENCE", 0.45))
            if float(confidence) < min_confidence:
                return DoctorAIAssistantSafetyLevel.LOW_CONFIDENCE
        except Exception:
            logger.debug("Failed to parse RAG confidence for assistant safety mapping")

    return DoctorAIAssistantSafetyLevel.DOCTOR_ONLY


def build_doctor_ai_message_from_rag_response(
    *,
    consultation,
    doctor,
    patient,
    rag_response,
    source_report=None,
    source_medical_record_entry=None,
):
    service_context = rag_response.rag_query.service_context
    if service_context == RAGServiceContext.REPORT_CASE_UPDATE:
        title = "AI case update from uploaded medical report"
        trigger_type = DoctorAIAssistantTriggerType.MEDICAL_REPORT_CASE_UPDATE
    elif service_context == RAGServiceContext.CONSULTATION:
        title = "AI consultation support update"
        trigger_type = DoctorAIAssistantTriggerType.CONSULTATION_CONTEXT_UPDATE
    elif service_context == RAGServiceContext.LAB_RESULT:
        title = "AI lab result support update"
        trigger_type = DoctorAIAssistantTriggerType.LAB_RESULT_CONTEXT_UPDATE
    else:
        title = "AI case support update"
        trigger_type = DoctorAIAssistantTriggerType.MANUAL_RAG_CASE_UPDATE

    safety = (rag_response.raw_response or {}).get("safety", {})
    summary = {
        "rag_response_id": str(rag_response.id),
        "rag_query_id": str(rag_response.rag_query_id),
        "service_context": service_context,
        "source_count": safety.get("source_count")
        if safety.get("source_count") is not None
        else rag_response.rag_query.retrieved_chunks.count(),
        "document_titles": _safe_document_titles(rag_response),
        "confidence": safety.get("confidence"),
        "fallback_reason": safety.get("fallback_reason"),
        "source_report_id": str(source_report.id) if source_report else None,
        "linked_medical_record_entry_id": (
            str(source_medical_record_entry.id) if source_medical_record_entry else None
        ),
    }

    source_metadata = {
        "service_context": service_context,
        "source_count": summary["source_count"],
        "document_titles": summary["document_titles"],
        "fallback_reason": summary["fallback_reason"],
    }

    return {
        "consultation": consultation,
        "doctor": doctor,
        "patient": patient,
        "trigger_type": trigger_type,
        "safety_level": _determine_safety_level(rag_response),
        "title": title,
        "body": (rag_response.response_text or "").strip(),
        "summary": summary,
        "source_report": source_report,
        "source_rag_response": rag_response,
        "source_medical_record_entry": source_medical_record_entry,
        "source_metadata": source_metadata,
    }


def _broadcast_doctor_ai_message_created(message):
    try:
        from apps.realtime.services import broadcast_doctor_ai_message_created

        broadcast_doctor_ai_message_created(message)
    except Exception:
        logger.exception(
            "Failed to broadcast doctor_ai.message.created",
            extra={"message_id": str(message.id), "doctor_id": str(message.doctor_id)},
        )


def _broadcast_doctor_ai_message_updated(message):
    try:
        from apps.realtime.services import broadcast_doctor_ai_message_updated

        broadcast_doctor_ai_message_updated(message)
    except Exception:
        logger.exception(
            "Failed to broadcast doctor_ai.message.updated",
            extra={"message_id": str(message.id), "doctor_id": str(message.doctor_id)},
        )


def create_doctor_ai_assistant_message(
    *,
    consultation,
    doctor,
    patient,
    title,
    body,
    trigger_type,
    safety_level,
    source_report=None,
    source_rag_response=None,
    source_medical_record_entry=None,
    summary=None,
    source_metadata=None,
    request=None,
):
    from .permissions import can_list_doctor_ai_messages_for_consultation

    if not can_list_doctor_ai_messages_for_consultation(doctor, consultation):
        raise PermissionError("You are not allowed to create assistant messages for this case.")

    message = DoctorAIAssistantMessage(
        consultation=consultation,
        doctor=doctor,
        patient=patient,
        trigger_type=trigger_type,
        status=DoctorAIAssistantMessageStatus.UNREAD,
        safety_level=safety_level,
        title=(title or "").strip()[:255],
        body=(body or "").strip(),
        summary=summary or {},
        source_report=source_report,
        source_rag_response=source_rag_response,
        source_medical_record_entry=source_medical_record_entry,
        source_metadata=source_metadata or {},
    )
    message.full_clean()
    message.save()

    create_audit_log(
        actor=doctor,
        action="doctor_ai_assistant_message_created",
        target=message,
        metadata={
            "consultation_id": str(consultation.id),
            "doctor_id": str(doctor.id),
            "patient_id": str(patient.id),
            "message_id": str(message.id),
            "trigger_type": trigger_type,
            "safety_level": safety_level,
            "source_report_id": str(source_report.id) if source_report else None,
            "source_rag_response_id": str(source_rag_response.id) if source_rag_response else None,
        },
        request=request,
    )

    try:
        create_notification(
            recipient=doctor,
            notification_type=NotificationType.CONSULTATION,
            title="AI case update is ready",
            message="AI case update is ready for review.",
            data={
                "consultation_id": str(consultation.id),
                "doctor_ai_message_id": str(message.id),
            },
        )
    except Exception:
        logger.exception(
            "Failed to notify doctor about assistant message",
            extra={"message_id": str(message.id), "doctor_id": str(doctor.id)},
        )

    transaction.on_commit(lambda: _broadcast_doctor_ai_message_created(message), robust=True)

    return message


def generate_doctor_ai_message_for_report(
    *,
    doctor,
    report,
    question=None,
    top_k=None,
    filters=None,
    force=False,
    create_if_exists=False,
    save_rag_response=True,
    request=None,
    llm_client=None,
):
    from .permissions import can_list_doctor_ai_messages_for_consultation

    consultation = report.consultation
    if consultation is None:
        raise ValueError("Medical report must be linked to a consultation.")

    if not can_list_doctor_ai_messages_for_consultation(doctor, consultation):
        raise PermissionError("You do not have permission to generate assistant updates.")

    existing = (
        DoctorAIAssistantMessage.objects.filter(
            consultation=consultation,
            doctor=doctor,
            source_report=report,
            source_rag_response__isnull=False,
            trigger_type=DoctorAIAssistantTriggerType.MEDICAL_REPORT_CASE_UPDATE,
        )
        .select_related("source_rag_response")
        .order_by("-created_at")
        .first()
    )
    if existing and not force and not create_if_exists:
        return existing

    _, rag_response = run_medical_report_case_update_rag(
        doctor=doctor,
        report=report,
        question=question,
        top_k=top_k,
        filters=filters,
        request=request,
        llm_client=llm_client,
    )

    payload = build_doctor_ai_message_from_rag_response(
        consultation=consultation,
        doctor=doctor,
        patient=report.patient,
        rag_response=rag_response,
        source_report=report,
        source_medical_record_entry=report.linked_medical_record_entry,
    )
    if not save_rag_response:
        payload["source_rag_response"] = None

    return create_doctor_ai_assistant_message(request=request, **payload)


def mark_doctor_ai_message_read(message, doctor, read=True, request=None):
    if message.doctor_id != doctor.id:
        raise PermissionError("You are not allowed to update this assistant message.")

    if read:
        message.status = DoctorAIAssistantMessageStatus.READ
        message.read_at = timezone.now()
        message.archived_at = None
    else:
        message.status = DoctorAIAssistantMessageStatus.UNREAD
        message.read_at = None

    message.save(update_fields=["status", "read_at", "updated_at", "archived_at"])

    create_audit_log(
        actor=doctor,
        action="doctor_ai_assistant_message_read_status_changed",
        target=message,
        metadata={
            "message_id": str(message.id),
            "doctor_id": str(doctor.id),
            "status": message.status,
            "read": bool(read),
        },
        request=request,
    )

    transaction.on_commit(lambda: _broadcast_doctor_ai_message_updated(message), robust=True)

    return message
