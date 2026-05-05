"""
Phase 12E — RAG evaluation dataset exporters.

Exports anonymized AI evaluation data for model improvement research.

Privacy rules enforced:
- No patient names, emails, phone numbers, or national IDs.
- No raw prescription/lab values tied to patient identity.
- object_id is hashed when anonymize=True.
- requested_by identifier is hashed (not exposed) when anonymize=True.
- Raw embeddings are never exported.
- query_text / response_text are excluded when include_text=False.
"""

from __future__ import annotations

import csv
import hashlib
import io


def hash_identifier(value: str, salt: str = "") -> str:
    """
    Return a stable SHA-256 hex digest for the given value + salt.

    The salt is derived from EXPORT_HASH_SALT setting (falls back to SECRET_KEY).
    This allows consistent hashing across exports while keeping raw IDs private.
    """
    from django.conf import settings as django_settings

    if not salt:
        salt = getattr(django_settings, "EXPORT_HASH_SALT", None) or getattr(
            django_settings, "SECRET_KEY", ""
        )
    material = f"{salt}:{value}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _build_record(
    rag_response,
    include_text: bool,
    anonymize: bool,
) -> dict:
    """
    Build one export record from a RAGResponse and its related objects.

    Joins: RAGQuery, RAGRetrievedChunk (+ KnowledgeChunk + KnowledgeDocument),
    RAGResponseFeedback, RAGRetrievedChunkFeedback.
    """
    rag_query = rag_response.rag_query

    # -- Doctor identifier --------------------------------------------------
    if anonymize:
        doctor_id_export = hash_identifier(str(rag_query.requested_by_id))
    else:
        doctor_id_export = str(rag_query.requested_by_id)

    # -- object_id ----------------------------------------------------------
    object_id_export = None
    if rag_query.object_id:
        if anonymize:
            object_id_export = hash_identifier(str(rag_query.object_id))
        else:
            object_id_export = str(rag_query.object_id)

    # -- Base record fields -------------------------------------------------
    record: dict = {
        "rag_query_id": str(rag_query.pk),
        "service_context": rag_query.service_context,
        "response_status": rag_response.status,
        "model_name": rag_response.model_name,
        "provider": rag_response.provider,
        "safety_level": rag_response.safety_level,
        "doctor_review_required": rag_response.doctor_review_required,
        "patient_visible": rag_response.patient_visible,
        "token_input": rag_response.token_input,
        "token_output": rag_response.token_output,
        "doctor_id_hash": doctor_id_export,
        "object_id_hash": object_id_export,
        "created_date": rag_query.created_at.date().isoformat() if rag_query.created_at else None,
    }

    # -- Text fields (opt-in) -----------------------------------------------
    if include_text:
        record["query_text"] = rag_query.query_text
        record["response_text"] = rag_response.response_text

    # -- Feedback -----------------------------------------------------------
    feedback_data: dict | None = None
    try:
        fb = rag_response.feedback
        feedback_data = {
            "rating": fb.rating,
            "is_source_grounded": fb.is_source_grounded,
            "is_clinically_useful": fb.is_clinically_useful,
            "is_safe": fb.is_safe,
            "needs_admin_review": fb.needs_admin_review,
            "review_status": fb.review_status,
        }
    except Exception:
        # No feedback submitted yet
        feedback_data = None

    record["feedback"] = feedback_data

    # -- Sources (retrieved chunks) ----------------------------------------
    sources = []
    for rc in rag_response.rag_query.retrieved_chunks.select_related("chunk__document").order_by(
        "rank"
    ):
        chunk = rc.chunk
        doc = chunk.document

        source_relevance = None
        try:
            # Look for source-level feedback on this chunk
            cf = rc.feedback_items.first()
            if cf:
                source_relevance = cf.relevance
        except Exception:
            pass

        sources.append(
            {
                "chunk_id": str(chunk.pk),
                "document_id": str(doc.pk),
                "document_title": doc.title,
                "document_type": doc.document_type,
                "rank": rc.rank,
                "score": round(rc.score, 6) if rc.score is not None else None,
                "source_relevance": source_relevance,
            }
        )

    record["sources"] = sources
    return record


def export_rag_evaluation_dataset(
    format: str = "json",
    include_text: bool = False,
    anonymize: bool = True,
) -> str | list[dict]:
    """
    Export RAG evaluation dataset.

    Args:
        format: "json" or "csv".
        include_text: If True, include query_text and response_text.
        anonymize: If True, hash doctor IDs and object IDs; exclude raw identifiers.

    Returns:
        For "json": Python list of dicts.
        For "csv": UTF-8 string of CSV content.

    Raises:
        ValueError: if format is not json or csv.
    """
    if format not in ("json", "csv"):
        raise ValueError(f"Unsupported export format: {format!r}. Use 'json' or 'csv'.")

    from .models import RAGResponse

    responses = (
        RAGResponse.objects.select_related(
            "rag_query__requested_by",
        )
        .prefetch_related(
            "rag_query__retrieved_chunks__chunk__document",
            "rag_query__retrieved_chunks__feedback_items",
            "feedback",
        )
        .order_by("rag_query__created_at")
    )

    records = [_build_record(r, include_text=include_text, anonymize=anonymize) for r in responses]

    if format == "json":
        return records

    # ── CSV export ──────────────────────────────────────────────────────────
    # Flatten the nested feedback/sources dicts to CSV-friendly columns.
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    header = [
        "rag_query_id",
        "service_context",
        "response_status",
        "model_name",
        "provider",
        "safety_level",
        "doctor_review_required",
        "patient_visible",
        "token_input",
        "token_output",
        "doctor_id_hash",
        "object_id_hash",
        "created_date",
        "feedback_rating",
        "feedback_is_source_grounded",
        "feedback_is_clinically_useful",
        "feedback_is_safe",
        "feedback_needs_admin_review",
        "feedback_review_status",
        "source_chunk_ids",
        "source_document_ids",
        "source_document_titles",
        "source_document_types",
        "source_ranks",
        "source_scores",
        "source_relevances",
    ]

    if include_text:
        header = ["query_text", "response_text"] + header

    writer.writerow(header)

    for rec in records:
        fb = rec.get("feedback") or {}
        sources = rec.get("sources") or []

        source_chunk_ids = "|".join(str(s["chunk_id"]) for s in sources)
        source_doc_ids = "|".join(str(s["document_id"]) for s in sources)
        source_doc_titles = "|".join(s["document_title"] for s in sources)
        source_doc_types = "|".join(s["document_type"] for s in sources)
        source_ranks = "|".join(str(s["rank"]) for s in sources)
        source_scores = "|".join(str(s["score"]) for s in sources)
        source_relevances = "|".join(str(s["source_relevance"]) for s in sources)

        row = [
            rec.get("rag_query_id", ""),
            rec.get("service_context", ""),
            rec.get("response_status", ""),
            rec.get("model_name", ""),
            rec.get("provider", ""),
            rec.get("safety_level", ""),
            rec.get("doctor_review_required", ""),
            rec.get("patient_visible", ""),
            rec.get("token_input", ""),
            rec.get("token_output", ""),
            rec.get("doctor_id_hash", ""),
            rec.get("object_id_hash", ""),
            rec.get("created_date", ""),
            fb.get("rating", ""),
            fb.get("is_source_grounded", ""),
            fb.get("is_clinically_useful", ""),
            fb.get("is_safe", ""),
            fb.get("needs_admin_review", ""),
            fb.get("review_status", ""),
            source_chunk_ids,
            source_doc_ids,
            source_doc_titles,
            source_doc_types,
            source_ranks,
            source_scores,
            source_relevances,
        ]

        if include_text:
            row = [rec.get("query_text", ""), rec.get("response_text", "")] + row

        writer.writerow(row)

    return output.getvalue()
