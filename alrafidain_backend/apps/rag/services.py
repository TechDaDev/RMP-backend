"""
RAG service layer — orchestrates semantic search, prompt building, and DeepSeek LLM calls.
"""

from __future__ import annotations

from django.conf import settings

from apps.audit.services import create_audit_log
from apps.common.choices import RAGResponseStatus, RAGSafetyLevel, RAGServiceContext

from .permissions import is_approved_doctor
from .prompting import build_doctor_rag_prompt


def doctor_can_use_rag(user) -> bool:
    """Return True if the user is allowed to use the RAG endpoints."""
    return is_approved_doctor(user)


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
    from .llm_clients.deepseek_client import DeepSeekClient
    from .models import RAGQuery, RAGResponse, RAGRetrievedChunk
    from apps.knowledge_base.services import semantic_search_approved_chunks

    if not doctor_can_use_rag(doctor):
        raise PermissionError("Only approved doctors may use the RAG endpoint.")

    if filters is None:
        filters = {}
    if top_k is None:
        top_k = getattr(settings, "RAG_DEFAULT_TOP_K", 6)
    top_k = min(top_k, getattr(settings, "RAG_MAX_TOP_K", 12))

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

    model_name = getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")

    # 3. No-context path
    if not hits:
        rag_response = RAGResponse.objects.create(
            rag_query=rag_query,
            response_text=(
                "No approved medical knowledge was found for your query. "
                "Please refine your question or contact a specialist."
            ),
            provider="deepseek",
            model_name=model_name,
            status=RAGResponseStatus.NO_CONTEXT,
            safety_level=RAGSafetyLevel.DOCTOR_ONLY,
        )
        create_audit_log(
            actor=doctor,
            action="rag_query_performed",
            metadata={
                "rag_query_id": str(rag_query.pk),
                "service_context": service_context,
                "status": RAGResponseStatus.NO_CONTEXT,
                "chunk_count": 0,
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
            for hit in hits
        ]
    )

    # 5. Build prompt
    messages = build_doctor_rag_prompt(
        query_text=query_text,
        retrieved_chunks=hits,
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
        response_text = result["content"]
        raw_response = result.get("raw", {})
        usage = result.get("usage", {})
        token_input = usage.get("prompt_tokens")
        token_output = usage.get("completion_tokens")
        model_name = result.get("model", model_name)
    except Exception as exc:
        status = RAGResponseStatus.FAILED
        response_text = "LLM call failed. Please try again."
        error_message = str(exc)

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
            "chunk_count": len(hits),
            "model": model_name,
        },
        request=request,
    )

    return rag_query, rag_response


def build_consultation_summary_for_rag(consultation) -> str:
    """Build a plain-text clinical summary of a consultation for use as RAG object_summary."""
    parts = [
        f"Consultation ID: {consultation.pk}",
        f"Status: {consultation.status}",
        f"Specialty: {consultation.selected_specialty or 'N/A'}",
    ]
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
            f"Numeric value: {lab_result.numeric_value} {unit} "
            f"(reference: {ref or 'N/A'})"
        )
    if getattr(lab_result, "text_value", None):
        parts.append(f"Text value: {lab_result.text_value}")
    if getattr(lab_result, "flag", None):
        parts.append(f"Flag: {lab_result.flag}")
    if getattr(lab_result, "laboratorian_notes", None):
        parts.append(f"Laboratorian notes: {lab_result.laboratorian_notes}")
    if getattr(lab_result, "doctor_notes", None):
        parts.append(f"Doctor notes: {lab_result.doctor_notes}")

    return "\n".join(parts)
