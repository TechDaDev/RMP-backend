"""
RAG service layer — orchestrates semantic search, prompt building, and DeepSeek LLM calls.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    KnowledgeApprovalStatus,
    KnowledgeProcessingStatus,
    KnowledgeSecurityStatus,
    MedicalRecordCategory,
    RAGFeedbackRating,
    RAGFeedbackReviewStatus,
    RAGResponseStatus,
    RAGSafetyLevel,
    RAGServiceContext,
)
from apps.common.report_extraction import extract_clinical_report_text, secure_extracted_report_text

from .permissions import can_access_consultation_rag, can_access_lab_result_rag, is_approved_doctor
from .prompting import build_doctor_rag_prompt

SAFE_FALLBACK_MESSAGE = (
    "I could not find enough approved source material to answer this safely. "
    "Please review the patient context and approved knowledge sources manually."
)

DEFAULT_REPORT_CASE_UPDATE_QUESTION = (
    "Based on the newly processed patient-uploaded medical report and consultation context, "
    "provide a doctor-facing case update summary, clinically relevant findings to verify, "
    "red flags to check, suggested follow-up questions, and source-grounded considerations. "
    "Do not diagnose or prescribe."
)


def _is_source_enforced_by_text(response_text: str) -> bool:
    normalized = (response_text or "").lower()
    return any(token in normalized for token in ("source", "sources", "citation", "[1]"))


def _compute_confidence(hits: list[dict]) -> float:
    if not hits:
        return 0.0
    scored = [float(h.get("score") or 0.0) for h in hits[:3]]
    if not scored:
        return 0.0
    avg_score = sum(scored) / len(scored)
    return round(max(0.0, min(1.0, avg_score)), 4)


def _filter_safe_hits(hits: list[dict]) -> list[dict]:
    safe_hits: list[dict] = []
    for hit in hits:
        chunk = hit.get("chunk")
        document = getattr(chunk, "document", None)
        if document is None:
            continue

        if getattr(document, "approval_status", None) != KnowledgeApprovalStatus.APPROVED:
            continue
        if getattr(document, "is_active", False) is not True:
            continue
        if getattr(chunk, "is_active", False) is not True:
            continue
        if getattr(document, "processing_status", None) not in {
            KnowledgeProcessingStatus.EXTRACTED,
            KnowledgeProcessingStatus.CHUNKED,
        }:
            continue
        if getattr(document, "security_status", None) not in {
            KnowledgeSecurityStatus.SCAN_CLEAN,
            KnowledgeSecurityStatus.SCAN_SKIPPED,
        }:
            continue
        safe_hits.append(hit)
    return safe_hits


def _build_safety_metadata(
    hits: list[dict], confidence: float, fallback_reason: str | None
) -> dict:
    source_docs: dict[str, str] = {}
    chunk_ids: list[str] = []
    retrieval_scores: list[float] = []

    for hit in hits[:20]:
        chunk = hit.get("chunk")
        doc = getattr(chunk, "document", None)
        if chunk is not None:
            chunk_ids.append(str(getattr(chunk, "pk", "")))
        if doc is not None:
            source_docs[str(getattr(doc, "pk", ""))] = str(getattr(doc, "title", ""))
        retrieval_scores.append(float(hit.get("score") or 0.0))

    return {
        "confidence": confidence,
        "fallback_reason": fallback_reason,
        "source_count": len(hits),
        "chunk_ids": chunk_ids,
        "document_ids": list(source_docs.keys()),
        "document_titles": list(source_docs.values()),
        "retrieval_scores": [round(v, 6) for v in retrieval_scores[:20]],
    }


def doctor_can_use_rag(user) -> bool:
    """Return True if the user is allowed to use the RAG endpoints."""
    return is_approved_doctor(user)


def _truncate_case_text(text: str, max_chars: int) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars].rstrip()}..."


def _safe_report_structured_observations(report) -> str:
    payload = report.structured_payload if isinstance(report.structured_payload, dict) else {}
    structured_data = payload.get("structured_data")
    if not isinstance(structured_data, dict) or not structured_data:
        return ""

    observations = []
    for key in ["lab_values", "findings", "impression", "observations", "sections"]:
        value = structured_data.get(key)
        if value is None:
            continue
        observations.append(f"{key}: {_truncate_case_text(str(value), 350)}")

    if not observations:
        return _truncate_case_text(str(structured_data), 500)
    return _truncate_case_text("; ".join(observations), 1200)


def build_medical_report_case_summary_for_rag(report) -> str:
    max_chars = int(getattr(settings, "RAG_REPORT_CASE_CONTEXT_MAX_CHARS", 6000))

    consultation = getattr(report, "consultation", None)
    lines = [f"Medical report ID: {report.pk}"]
    lines.append(f"Report type: {report.report_type}")
    lines.append(f"Processing status: {report.processing_status}")
    lines.append(f"Is medical report: {bool(report.is_medical_report)}")

    if report.detected_language:
        lines.append(f"Detected language: {report.detected_language}")
    if report.llm_confidence is not None:
        lines.append(f"LLM confidence: {float(report.llm_confidence):.4f}")

    if consultation is not None:
        lines.append(f"Consultation ID: {consultation.pk}")
        lines.append(f"Consultation status: {consultation.status}")
        specialty = consultation.selected_specialty or consultation.recommended_specialty or "N/A"
        lines.append(f"Consultation specialty: {specialty}")

        symptom_flags = []
        if getattr(consultation, "has_fever", False):
            symptom_flags.append("fever")
        if getattr(consultation, "has_pain", False):
            symptom_flags.append("pain")
        if getattr(consultation, "has_breathing_difficulty", False):
            symptom_flags.append("breathing_difficulty")
        if getattr(consultation, "has_emergency_warning", False):
            symptom_flags.append("emergency_warning")
        if symptom_flags:
            lines.append(f"Consultation symptom flags: {', '.join(symptom_flags)}")

        if getattr(consultation, "current_medications_related", ""):
            lines.append(
                "Current medications related: "
                + _truncate_case_text(consultation.current_medications_related, 600)
            )
        if getattr(consultation, "additional_notes", ""):
            lines.append(
                "Consultation additional notes: "
                + _truncate_case_text(consultation.additional_notes, 700)
            )

    if report.cleaned_report_text:
        lines.append(
            "Cleaned report text: " + _truncate_case_text(report.cleaned_report_text, 3000)
        )

    structured_obs = _safe_report_structured_observations(report)
    if structured_obs:
        lines.append(f"Structured observations: {structured_obs}")

    linked_entry = getattr(report, "linked_medical_record_entry", None)
    if linked_entry is not None:
        lines.append(
            "Linked medical record entry: "
            f"id={linked_entry.pk}, category={linked_entry.category}, "
            f"title={_truncate_case_text(linked_entry.title, 160)}, "
            f"verification_status={linked_entry.verification_status}"
        )

    if report.doctor_notes:
        lines.append("Doctor notes: " + _truncate_case_text(report.doctor_notes, 600))

    lines.append(
        "Safety note: This report was patient-uploaded and AI-extracted; "
        "clinical validation is required."
    )

    return _truncate_case_text("\n".join(lines), max_chars)


def doctor_can_access_medical_report_rag(doctor, report) -> bool:
    if not doctor_can_use_rag(doctor):
        return False

    from apps.patient_records.permissions import can_view_medical_report

    return can_view_medical_report(doctor, report)


def run_medical_report_case_update_rag(
    *,
    doctor,
    report,
    question=None,
    top_k=None,
    filters=None,
    request=None,
    llm_client=None,
):
    if not doctor_can_access_medical_report_rag(doctor, report):
        raise PermissionError("You do not have permission to run RAG case update for this report.")

    allowed_statuses = {
        "llm_completed",
        "doctor_reviewed",
        "accepted",
    }
    if not report.is_medical_report or report.processing_status not in allowed_statuses:
        raise ValueError("Report must be an accepted medical report before running case update.")

    payload = report.structured_payload if isinstance(report.structured_payload, dict) else {}
    structured_data = payload.get("structured_data") if isinstance(payload, dict) else None
    has_structured_data = isinstance(structured_data, dict) and bool(structured_data)
    has_cleaned_text = bool((report.cleaned_report_text or "").strip())
    has_linked_entry = bool(report.linked_medical_record_entry_id)

    if not (has_cleaned_text or has_structured_data or has_linked_entry):
        raise ValueError("Report does not have enough structured context for case update.")

    summary = build_medical_report_case_summary_for_rag(report)
    query_text = (question or "").strip() or DEFAULT_REPORT_CASE_UPDATE_QUESTION

    safe_filters = {}
    filters = filters or {}
    for key in ["document_type", "specialty", "language", "audience"]:
        value = filters.get(key)
        if value:
            safe_filters[key] = value

    return run_doctor_rag_query(
        doctor=doctor,
        query_text=query_text,
        service_context=RAGServiceContext.REPORT_CASE_UPDATE,
        object_id=report.pk,
        filters=safe_filters,
        top_k=top_k,
        object_summary=summary,
        request=request,
        llm_client=llm_client,
    )


def run_doctor_rag_query(
    doctor,
    query_text: str,
    service_context: str,
    object_id=None,
    filters: dict | None = None,
    top_k: int | None = None,
    object_summary: str | None = None,
    llm_client=None,
    request=None,
):
    """
    Full RAG pipeline for doctor queries.

    1. Validate doctor is approved.
    2. Persist RAGQuery.
    3. Semantic search approved knowledge base chunks.
    4. If no chunks → persist RAGResponse(status=no_context), audit, return.
    5. Persist RAGRetrievedChunk records.
    6. Build prompt and call DeepSeek.
    7. Persist RAGResponse(status=success or failed).
    8. Audit.
    9. Return (rag_query, rag_response) tuple.
    """
    from apps.knowledge_base.services import semantic_search_approved_chunks

    from .llm_clients.deepseek_client import DeepSeekClient
    from .models import RAGQuery, RAGResponse, RAGRetrievedChunk

    if not doctor_can_use_rag(doctor):
        raise PermissionError("Only approved doctors may use the RAG endpoint.")

    if filters is None:
        filters = {}
    if top_k is None:
        top_k = getattr(settings, "RAG_DEFAULT_TOP_K", 6)
    top_k = min(
        top_k,
        getattr(settings, "RAG_MAX_TOP_K", 12),
        getattr(settings, "RAG_MAX_CONTEXT_CHUNKS", 5),
    )

    # 1. Persist query
    rag_query = RAGQuery.objects.create(
        requested_by=doctor,
        service_context=service_context,
        object_id=object_id,
        query_text=query_text,
        role_context="doctor",
        top_k=top_k,
        filters=filters,
    )

    # 2. Semantic search
    hits = semantic_search_approved_chunks(
        query=query_text,
        document_type=filters.get("document_type"),
        specialty=filters.get("specialty"),
        language=filters.get("language"),
        audience=filters.get("audience"),
        limit=top_k,
        actor=doctor,
        request=request,
    )
    safe_hits = _filter_safe_hits(hits)
    require_sources = getattr(settings, "RAG_REQUIRE_SOURCES", True)
    min_confidence = float(getattr(settings, "RAG_MIN_CONFIDENCE", 0.45))
    confidence = _compute_confidence(safe_hits)

    model_name = getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")

    fallback_reason = None
    if not safe_hits:
        fallback_reason = "no_approved_context"
    elif require_sources and len(safe_hits) == 0:
        fallback_reason = "sources_required"
    elif confidence < min_confidence:
        fallback_reason = "low_confidence"

    # 3. No-context / low-confidence path
    if fallback_reason is not None:
        safety_metadata = _build_safety_metadata(safe_hits, confidence, fallback_reason)
        rag_response = RAGResponse.objects.create(
            rag_query=rag_query,
            response_text=SAFE_FALLBACK_MESSAGE,
            provider="deepseek",
            model_name=model_name,
            status=RAGResponseStatus.NO_CONTEXT,
            safety_level=RAGSafetyLevel.DOCTOR_ONLY,
            raw_response={"safety": safety_metadata},
        )
        create_audit_log(
            actor=doctor,
            action="rag_query_performed",
            metadata={
                "rag_query_id": str(rag_query.pk),
                "service_context": service_context,
                "status": RAGResponseStatus.NO_CONTEXT,
                "chunk_count": len(safe_hits),
                "confidence": confidence,
                "fallback_reason": fallback_reason,
            },
            request=request,
        )
        return rag_query, rag_response

    # 4. Persist retrieved chunks
    RAGRetrievedChunk.objects.bulk_create(
        [
            RAGRetrievedChunk(
                rag_query=rag_query,
                chunk=hit["chunk"],
                rank=hit["rank"],
                score=hit["score"],
                distance=hit.get("distance"),
            )
            for hit in safe_hits
        ]
    )

    # 5. Build prompt
    messages = build_doctor_rag_prompt(
        query_text=query_text,
        retrieved_chunks=safe_hits,
        service_context=service_context,
        object_summary=object_summary,
    )
    prompt_text = "\n".join(m["content"] for m in messages)

    # 6. Call LLM
    if llm_client is None:
        llm_client = DeepSeekClient()

    status = RAGResponseStatus.SUCCESS
    response_text = ""
    raw_response: dict = {}
    error_message = None
    token_input = None
    token_output = None

    try:
        result = llm_client.chat(messages)
        response_text = (result.get("content") or "")[
            : getattr(settings, "RAG_MAX_ANSWER_LENGTH", 4000)
        ]
        raw_response = result.get("raw", {})
        usage = result.get("usage", {})
        usage_summary = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
            "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
        }
        token_input = usage.get("prompt_tokens")
        token_output = usage.get("completion_tokens")
        model_name = result.get("model", model_name)

        if isinstance(raw_response, dict):
            raw_response = {**raw_response, "usage_summary": usage_summary}
        else:
            raw_response = {"usage_summary": usage_summary}

        if require_sources and not _is_source_enforced_by_text(response_text):
            status = RAGResponseStatus.NO_CONTEXT
            response_text = SAFE_FALLBACK_MESSAGE
            fallback_reason = "missing_citations"
    except Exception as exc:
        status = RAGResponseStatus.FAILED
        response_text = "LLM call failed. Please try again."
        error_message = str(exc)
        fallback_reason = "llm_error"

    safety_metadata = _build_safety_metadata(safe_hits, confidence, fallback_reason)
    if isinstance(raw_response, dict):
        raw_response = {**raw_response, "safety": safety_metadata}
    else:
        raw_response = {"safety": safety_metadata}

    # 7. Persist response
    rag_response = RAGResponse.objects.create(
        rag_query=rag_query,
        response_text=response_text,
        provider="deepseek",
        model_name=model_name,
        status=status,
        safety_level=RAGSafetyLevel.DOCTOR_ONLY,
        prompt_text=prompt_text,
        raw_response=raw_response,
        error_message=error_message,
        token_input=token_input,
        token_output=token_output,
    )

    # 8. Audit
    create_audit_log(
        actor=doctor,
        action="rag_query_performed",
        metadata={
            "rag_query_id": str(rag_query.pk),
            "service_context": service_context,
            "status": status,
            "chunk_count": len(safe_hits),
            "confidence": confidence,
            "fallback_reason": fallback_reason,
            "model": model_name,
        },
        request=request,
    )

    return rag_query, rag_response


def _resolve_patient_and_context_for_rag_response(rag_query, doctor):
    if not rag_query.object_id:
        raise ValueError("This RAG response has no clinical object context to persist.")

    if rag_query.service_context == RAGServiceContext.CONSULTATION:
        from apps.consultations.models import Consultation

        consultation = Consultation.objects.filter(pk=rag_query.object_id).first()
        if consultation is None:
            raise ValueError("Consultation context was not found.")
        if not can_access_consultation_rag(doctor, consultation):
            raise PermissionError("You cannot persist this consultation RAG response.")

        return {
            "patient": consultation.patient,
            "title": f"AI Clinical Case Report (Consultation {consultation.pk})",
            "context_summary": build_consultation_summary_for_rag(consultation),
        }

    if rag_query.service_context == RAGServiceContext.LAB_RESULT:
        from apps.lab_orders.models import LabResult

        lab_result = LabResult.objects.filter(pk=rag_query.object_id).first()
        if lab_result is None:
            raise ValueError("Lab result context was not found.")
        if not can_access_lab_result_rag(doctor, lab_result):
            raise PermissionError("You cannot persist this lab-result RAG response.")

        return {
            "patient": lab_result.patient,
            "title": f"AI Clinical Case Report (Lab Result {lab_result.pk})",
            "context_summary": build_lab_result_summary_for_rag(lab_result),
        }

    raise ValueError("Only consultation and lab-result RAG responses can be persisted.")


def save_rag_response_to_patient_record(
    *,
    rag_response,
    doctor,
    physician_notes: str = "",
    request=None,
):
    from apps.patient_records.services import (
        create_medical_record_entry,
        get_or_create_patient_medical_record,
    )

    if not doctor_can_use_rag(doctor):
        raise PermissionError("Only approved doctors may persist RAG responses.")

    rag_query = rag_response.rag_query
    if rag_query.requested_by_id != doctor.pk:
        raise PermissionError("You can only persist your own RAG response.")

    if rag_response.status != RAGResponseStatus.SUCCESS:
        raise ValueError("Only successful RAG responses can be persisted.")

    raw_response = rag_response.raw_response if isinstance(rag_response.raw_response, dict) else {}
    if raw_response.get("saved_patient_record_entry_id"):
        raise ValueError("This RAG response was already saved to the patient record.")

    resolved = _resolve_patient_and_context_for_rag_response(rag_query, doctor)
    record = get_or_create_patient_medical_record(resolved["patient"])

    safety = raw_response.get("safety", {}) if isinstance(raw_response, dict) else {}
    source_titles = safety.get("document_titles") or []

    notes_parts = []
    if physician_notes.strip():
        notes_parts.append(f"Treating physician notes:\n{physician_notes.strip()}")
    notes_parts.append(f"RAG query: {rag_query.query_text}")
    if source_titles:
        notes_parts.append(f"Referenced sources: {', '.join(source_titles)}")
    notes_parts.append(f"Clinical context snapshot:\n{resolved['context_summary']}")

    entry = create_medical_record_entry(
        record=record,
        source_user=doctor,
        category=MedicalRecordCategory.GENERAL_NOTE,
        title=resolved["title"],
        value=rag_response.response_text,
        notes="\n\n".join(notes_parts),
        request=request,
    )

    rag_response.raw_response = {
        **raw_response,
        "saved_patient_record_entry_id": str(entry.id),
        "saved_patient_record_id": str(record.id),
        "saved_by_doctor_id": str(doctor.id),
        "saved_at": timezone.now().isoformat(),
    }
    rag_response.save(update_fields=["raw_response", "updated_at"])

    create_audit_log(
        actor=doctor,
        action="rag_response_saved_to_patient_record",
        target=entry,
        metadata={
            "rag_response_id": str(rag_response.id),
            "rag_query_id": str(rag_query.id),
            "patient_record_id": str(record.id),
            "medical_record_entry_id": str(entry.id),
            "service_context": rag_query.service_context,
            "object_id": str(rag_query.object_id) if rag_query.object_id else None,
        },
        request=request,
    )

    return entry


def build_consultation_summary_for_rag(consultation) -> str:
    """Build a plain-text clinical summary of a consultation for use as RAG object_summary."""
    parts = [
        f"Consultation ID: {consultation.pk}",
        f"Status: {consultation.status}",
        f"Specialty: {consultation.selected_specialty or 'N/A'}",
    ]
    ranked_specialties = []
    get_ranked = getattr(consultation, "get_recommended_specialties", None)
    if callable(get_ranked):
        ranked_specialties = get_ranked()
    elif getattr(consultation, "recommended_specialties", None):
        ranked_specialties = consultation.recommended_specialties
    if ranked_specialties:
        parts.append(f"Ranked specialties: {', '.join(ranked_specialties)}")

    if consultation.additional_notes:
        parts.append(f"Additional notes: {consultation.additional_notes}")
    if consultation.current_medications_related:
        parts.append(f"Current medications (related): {consultation.current_medications_related}")

    flags = []
    if getattr(consultation, "has_fever", False):
        flags.append("fever")
    if getattr(consultation, "has_pain", False):
        flags.append("pain")
    if getattr(consultation, "has_breathing_difficulty", False):
        flags.append("breathing difficulty")
    if getattr(consultation, "has_emergency_warning", False):
        flags.append("emergency warning signs")
    if flags:
        parts.append(f"Reported symptoms: {', '.join(flags)}")

    if getattr(consultation, "severity", None):
        parts.append(f"Severity: {consultation.severity}")
    if getattr(consultation, "duration", None):
        parts.append(f"Duration: {consultation.duration}")

    max_files = int(getattr(settings, "RAG_MAX_REPORT_FILES", 3))
    max_chars_per_file = int(getattr(settings, "RAG_REPORT_TEXT_CHARS_PER_FILE", 1500))

    attachments = []
    try:
        attachments = list(consultation.attachments.all()[:max_files])
    except Exception:
        attachments = []

    for attachment in attachments:
        extracted = extract_clinical_report_text(
            attachment.file,
            max_chars=max_chars_per_file,
        )
        if not extracted:
            continue

        secure_payload = secure_extracted_report_text(extracted)
        if not secure_payload["accepted"]:
            continue

        original_name = getattr(attachment, "original_name", "uploaded_report")
        parts.append(
            f"Patient report attachment ({original_name}) extracted text:\n"
            f"{secure_payload['sanitized_text']}"
        )

    return "\n".join(parts)


def build_lab_result_summary_for_rag(lab_result) -> str:
    """Build a plain-text clinical summary of a lab result for use as RAG object_summary."""
    try:
        test_name = lab_result.lab_order_item.test_name
    except Exception:
        test_name = "Unknown test"

    parts = [
        f"Lab Result ID: {lab_result.pk}",
        f"Test: {test_name}",
        f"Status: {lab_result.status}",
    ]

    if getattr(lab_result, "value_type", None):
        parts.append(f"Value type: {lab_result.value_type}")
    if getattr(lab_result, "numeric_value", None) is not None:
        unit = getattr(lab_result, "unit", "") or ""
        ref = getattr(lab_result, "reference_range", "") or ""
        parts.append(
            f"Numeric value: {lab_result.numeric_value} {unit} (reference: {ref or 'N/A'})"
        )
    if getattr(lab_result, "text_value", None):
        parts.append(f"Text value: {lab_result.text_value}")
    if getattr(lab_result, "flag", None):
        parts.append(f"Flag: {lab_result.flag}")
    if getattr(lab_result, "laboratorian_notes", None):
        parts.append(f"Laboratorian notes: {lab_result.laboratorian_notes}")
    if getattr(lab_result, "doctor_notes", None):
        parts.append(f"Doctor notes: {lab_result.doctor_notes}")

    result_file = getattr(lab_result, "result_file", None)
    if result_file:
        extracted = extract_clinical_report_text(
            result_file,
            max_chars=int(getattr(settings, "RAG_REPORT_TEXT_CHARS_PER_FILE", 1500)),
        )
        if extracted:
            secure_payload = secure_extracted_report_text(extracted)
            if secure_payload["accepted"]:
                parts.append(f"Uploaded report extracted text:\n{secure_payload['sanitized_text']}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 12D — Feedback services
# ---------------------------------------------------------------------------


def submit_rag_response_feedback(
    rag_response,
    doctor,
    rating: str,
    comment: str | None = None,
    is_source_grounded: bool | None = None,
    is_clinically_useful: bool | None = None,
    is_safe: bool = True,
    source_feedback: list[dict] | None = None,
    request=None,
):
    """
    Create feedback for a RAG response.

    Args:
        rag_response: RAGResponse instance.
        doctor: The User submitting feedback (must be rag_response.rag_query.requested_by).
        rating: RAGFeedbackRating value.
        comment: Optional free-text comment.
        is_source_grounded: Whether the answer was grounded in retrieved sources.
        is_clinically_useful: Whether the answer was clinically useful.
        is_safe: Whether the answer was safe.
        source_feedback: Optional list of {retrieved_chunk_id, relevance, comment} dicts.
        request: Django request for audit logging.

    Returns:
        RAGResponseFeedback instance.

    Raises:
        PermissionError: If doctor is not the one who requested the RAG response.
        ValueError: If feedback already exists for this response.
    """
    from .models import RAGResponseFeedback, RAGRetrievedChunk, RAGRetrievedChunkFeedback

    if rag_response.rag_query.requested_by_id != doctor.pk:
        raise PermissionError(
            "Only the doctor who requested this RAG response can submit feedback."
        )

    if RAGResponseFeedback.objects.filter(rag_response=rag_response).exists():
        raise ValueError("Feedback has already been submitted for this RAG response.")

    # Enforce safety escalation
    if rating == RAGFeedbackRating.UNSAFE:
        is_safe = False

    feedback = RAGResponseFeedback.objects.create(
        rag_response=rag_response,
        doctor=doctor,
        rating=rating,
        comment=comment,
        is_source_grounded=is_source_grounded,
        is_clinically_useful=is_clinically_useful,
        is_safe=is_safe,
    )

    # Process source feedback
    source_feedback_count = 0
    if source_feedback:
        valid_chunk_ids = {
            str(pk) for pk in rag_response.rag_query.retrieved_chunks.values_list("id", flat=True)
        }
        for sf in source_feedback:
            chunk_id = str(sf.get("retrieved_chunk_id", ""))
            if chunk_id not in valid_chunk_ids:
                raise ValueError(f"Retrieved chunk {chunk_id} does not belong to this RAG query.")
            try:
                chunk = RAGRetrievedChunk.objects.get(
                    id=chunk_id,
                    rag_query=rag_response.rag_query,
                )
            except RAGRetrievedChunk.DoesNotExist:
                raise ValueError(
                    f"Retrieved chunk {chunk_id} not found for this RAG query."
                ) from None
            RAGRetrievedChunkFeedback.objects.create(
                feedback=feedback,
                retrieved_chunk=chunk,
                relevance=sf.get("relevance", "unknown"),
                comment=sf.get("comment") or None,
            )
            source_feedback_count += 1

    create_audit_log(
        actor=doctor,
        action="rag_feedback_submitted",
        metadata={
            "rag_response_id": str(rag_response.pk),
            "rag_query_id": str(rag_response.rag_query_id),
            "doctor_id": str(doctor.pk),
            "rating": rating,
            "is_safe": is_safe,
            "needs_admin_review": feedback.needs_admin_review,
            "review_status": feedback.review_status,
            "source_feedback_count": source_feedback_count,
        },
        request=request,
    )

    return feedback


def review_rag_feedback(
    feedback,
    reviewer,
    review_status: str,
    review_notes: str | None = None,
    request=None,
):
    """
    Staff review of a RAG feedback item.

    Args:
        feedback: RAGResponseFeedback instance.
        reviewer: The User performing the review (must be staff or superuser).
        review_status: One of reviewed / dismissed / escalated.
        review_notes: Optional reviewer notes.
        request: Django request for audit logging.

    Returns:
        Updated RAGResponseFeedback instance.

    Raises:
        PermissionError: If reviewer is not staff or superuser.
        ValueError: If review_status is not a valid non-pending value.
    """
    allowed_statuses = {
        RAGFeedbackReviewStatus.REVIEWED,
        RAGFeedbackReviewStatus.DISMISSED,
        RAGFeedbackReviewStatus.ESCALATED,
    }

    if not (reviewer.is_staff or reviewer.is_superuser):
        raise PermissionError("Only staff or superusers may review RAG feedback.")

    if review_status not in allowed_statuses:
        raise ValueError(
            f"Invalid review_status '{review_status}'. Allowed: {sorted(allowed_statuses)}"
        )

    feedback.review_status = review_status
    feedback.reviewed_by = reviewer
    feedback.reviewed_at = timezone.now()
    feedback.review_notes = review_notes
    feedback.save(
        update_fields=["review_status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"]
    )

    create_audit_log(
        actor=reviewer,
        action="rag_feedback_reviewed",
        metadata={
            "rag_response_id": str(feedback.rag_response_id),
            "rag_query_id": str(feedback.rag_response.rag_query_id),
            "doctor_id": str(feedback.doctor_id),
            "rating": feedback.rating,
            "is_safe": feedback.is_safe,
            "needs_admin_review": feedback.needs_admin_review,
            "review_status": review_status,
        },
        request=request,
    )

    return feedback


def get_rag_feedback_summary() -> dict:
    """Return simple aggregate counts for admin dashboards."""
    from .models import RAGResponseFeedback

    qs = RAGResponseFeedback.objects.all()
    summary: dict = {"total": qs.count(), "by_rating": {}, "by_review_status": {}}

    from apps.common.choices import RAGFeedbackRating, RAGFeedbackReviewStatus

    for rating in RAGFeedbackRating.values:
        summary["by_rating"][rating] = qs.filter(rating=rating).count()
    for status in RAGFeedbackReviewStatus.values:
        summary["by_review_status"][status] = qs.filter(review_status=status).count()

    return summary
