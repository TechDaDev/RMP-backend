"""
Phase 12E — RAG analytics functions.

All aggregations are performed using Django ORM queries only.
No patient-identifiable data is included.
"""

from __future__ import annotations

from django.db.models import Avg, Count, Q, Sum


def get_rag_feedback_metrics() -> dict:
    """
    Return feedback coverage and quality metrics.

    Counts are over RAGResponse records (not RAGQuery) to measure
    how much of the AI output received structured doctor feedback.
    """
    from apps.common.choices import RAGFeedbackRating, RAGFeedbackReviewStatus
    from .models import RAGResponse, RAGResponseFeedback

    total_responses = RAGResponse.objects.count()
    responses_with_feedback = RAGResponseFeedback.objects.count()

    coverage_rate = (
        round(responses_with_feedback / total_responses, 4)
        if total_responses > 0
        else 0.0
    )

    ratings: dict[str, int] = {}
    for rating in RAGFeedbackRating.values:
        ratings[rating] = RAGResponseFeedback.objects.filter(rating=rating).count()

    review_status_counts: dict[str, int] = {}
    for status in RAGFeedbackReviewStatus.values:
        review_status_counts[status] = RAGResponseFeedback.objects.filter(
            review_status=status
        ).count()

    return {
        "total_responses": total_responses,
        "responses_with_feedback": responses_with_feedback,
        "feedback_coverage_rate": coverage_rate,
        "ratings": ratings,
        "unsafe_count": ratings.get(RAGFeedbackRating.UNSAFE, 0),
        "needs_admin_review_count": RAGResponseFeedback.objects.filter(
            needs_admin_review=True
        ).count(),
        "review_status": review_status_counts,
    }


def get_retrieval_quality_metrics() -> dict:
    """
    Return retrieval quality aggregates from RAGRetrievedChunk and their feedback.

    Average score across all retrieved chunks.
    Average rank of chunks rated 'relevant' via source feedback.
    """
    from apps.common.choices import RAGSourceRelevance
    from .models import RAGRetrievedChunk, RAGRetrievedChunkFeedback

    total_retrieved_chunks = RAGRetrievedChunk.objects.count()
    chunks_with_feedback = RAGRetrievedChunkFeedback.objects.values(
        "retrieved_chunk_id"
    ).distinct().count()

    source_relevance: dict[str, int] = {}
    for relevance in RAGSourceRelevance.values:
        source_relevance[relevance] = RAGRetrievedChunkFeedback.objects.filter(
            relevance=relevance
        ).count()

    avg_score_result = RAGRetrievedChunk.objects.aggregate(avg=Avg("score"))
    average_score = round(avg_score_result["avg"] or 0.0, 4)

    relevant_avg_rank = RAGRetrievedChunk.objects.filter(
        feedback_items__relevance=RAGSourceRelevance.RELEVANT
    ).aggregate(avg=Avg("rank"))
    avg_rank_of_relevant = round(relevant_avg_rank["avg"] or 0.0, 2)

    return {
        "total_retrieved_chunks": total_retrieved_chunks,
        "chunks_with_feedback": chunks_with_feedback,
        "source_relevance": source_relevance,
        "average_score": average_score,
        "average_rank_of_relevant_sources": avg_rank_of_relevant,
    }


def get_rag_usage_metrics() -> dict:
    """
    Return RAG usage aggregates per service context and response status.
    Includes total token counts.
    """
    from apps.common.choices import RAGResponseStatus, RAGServiceContext
    from .models import RAGQuery, RAGResponse

    total_queries = RAGQuery.objects.count()

    by_service_context: dict[str, int] = {}
    for ctx in RAGServiceContext.values:
        by_service_context[ctx] = RAGQuery.objects.filter(
            service_context=ctx
        ).count()

    by_status: dict[str, int] = {}
    for status in RAGResponseStatus.values:
        by_status[status] = RAGResponse.objects.filter(status=status).count()

    token_sums = RAGResponse.objects.aggregate(
        total_input=Sum("token_input"),
        total_output=Sum("token_output"),
    )

    return {
        "total_queries": total_queries,
        "by_service_context": by_service_context,
        "by_status": by_status,
        "total_token_input": token_sums["total_input"] or 0,
        "total_token_output": token_sums["total_output"] or 0,
    }


def get_rag_analytics_summary() -> dict:
    """
    Combine all analytics into a single payload for the admin API.
    """
    return {
        "feedback": get_rag_feedback_metrics(),
        "retrieval_quality": get_retrieval_quality_metrics(),
        "usage": get_rag_usage_metrics(),
    }
