from django.conf import settings
from rest_framework import serializers

from apps.common.choices import RAGFeedbackRating, RAGFeedbackReviewStatus, RAGSourceRelevance

from .models import (
    RAGResponse,
    RAGResponseFeedback,
    RAGRetrievedChunk,
    RAGRetrievedChunkFeedback,
)


class DoctorRAGQuerySerializer(serializers.Serializer):
    """Input serializer for the general doctor RAG query endpoint."""

    question = serializers.CharField(max_length=2000)
    document_type = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    specialty = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    language = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    audience = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    top_k = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    def validate_top_k(self, value):
        max_k = getattr(settings, "RAG_MAX_TOP_K", 12)
        if value > max_k:
            raise serializers.ValidationError(f"top_k may not exceed {max_k}.")
        return value

    def get_fields(self):
        fields = super().get_fields()
        default_k = getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        fields["top_k"].default = default_k
        return fields


class RAGRetrievedChunkSerializer(serializers.ModelSerializer):
    chunk_id = serializers.UUIDField(source="chunk.id", read_only=True)
    document_id = serializers.UUIDField(source="chunk.document.id", read_only=True)
    document_title = serializers.CharField(source="chunk.document.title", read_only=True)
    document_type = serializers.CharField(source="chunk.document.document_type", read_only=True)
    page_number = serializers.IntegerField(source="chunk.page_number", read_only=True)
    section_title = serializers.CharField(source="chunk.section_title", read_only=True)

    class Meta:
        model = RAGRetrievedChunk
        fields = [
            "chunk_id",
            "document_id",
            "document_title",
            "document_type",
            "page_number",
            "section_title",
            "rank",
            "score",
        ]


class RAGResponseSerializer(serializers.ModelSerializer):
    query_id = serializers.UUIDField(source="rag_query.id", read_only=True)
    service_context = serializers.CharField(source="rag_query.service_context", read_only=True)
    object_id = serializers.UUIDField(source="rag_query.object_id", read_only=True)
    sources = RAGRetrievedChunkSerializer(
        source="rag_query.retrieved_chunks",
        many=True,
        read_only=True,
    )

    class Meta:
        model = RAGResponse
        fields = [
            "id",
            "query_id",
            "service_context",
            "object_id",
            "response_text",
            "status",
            "safety_level",
            "doctor_review_required",
            "patient_visible",
            "sources",
            "model_name",
            "token_input",
            "token_output",
            "created_at",
        ]
        read_only_fields = fields


class ConsultationRAGSupportSerializer(serializers.Serializer):
    """Input serializer for the consultation RAG support endpoint."""

    question = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    top_k = serializers.IntegerField(required=False, min_value=1)

    def validate_top_k(self, value):
        max_k = getattr(settings, "RAG_MAX_TOP_K", 12)
        if value > max_k:
            raise serializers.ValidationError(f"top_k may not exceed {max_k}.")
        return value

    def get_fields(self):
        fields = super().get_fields()
        default_k = getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        fields["top_k"].default = default_k
        return fields


class LabResultRAGSupportSerializer(serializers.Serializer):
    """Input serializer for the lab result RAG support endpoint."""

    question = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    top_k = serializers.IntegerField(required=False, min_value=1)

    def validate_top_k(self, value):
        max_k = getattr(settings, "RAG_MAX_TOP_K", 12)
        if value > max_k:
            raise serializers.ValidationError(f"top_k may not exceed {max_k}.")
        return value

    def get_fields(self):
        fields = super().get_fields()
        default_k = getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        fields["top_k"].default = default_k
        return fields


# ---------------------------------------------------------------------------
# Phase 12D — Feedback serializers
# ---------------------------------------------------------------------------


class RAGRetrievedChunkFeedbackInputSerializer(serializers.Serializer):
    """Input for a single source chunk's relevance feedback."""

    retrieved_chunk_id = serializers.UUIDField()
    relevance = serializers.ChoiceField(
        choices=RAGSourceRelevance.choices,
        default=RAGSourceRelevance.UNKNOWN,
    )
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class RAGResponseFeedbackCreateSerializer(serializers.Serializer):
    """Input serializer for creating RAG feedback."""

    rating = serializers.ChoiceField(choices=RAGFeedbackRating.choices)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    is_source_grounded = serializers.BooleanField(required=False, allow_null=True, default=None)
    is_clinically_useful = serializers.BooleanField(required=False, allow_null=True, default=None)
    is_safe = serializers.BooleanField(required=False, default=True)
    source_feedback = RAGRetrievedChunkFeedbackInputSerializer(
        many=True, required=False, default=list
    )


class RAGRetrievedChunkFeedbackSerializer(serializers.ModelSerializer):
    retrieved_chunk_id = serializers.UUIDField(source="retrieved_chunk.id", read_only=True)
    chunk_rank = serializers.IntegerField(source="retrieved_chunk.rank", read_only=True)

    class Meta:
        model = RAGRetrievedChunkFeedback
        fields = [
            "id",
            "retrieved_chunk_id",
            "chunk_rank",
            "relevance",
            "comment",
            "created_at",
        ]
        read_only_fields = fields


class RAGResponseFeedbackSerializer(serializers.ModelSerializer):
    rag_response_id = serializers.UUIDField(source="rag_response.id", read_only=True)
    doctor_email = serializers.EmailField(source="doctor.email", read_only=True)
    reviewed_by_email = serializers.SerializerMethodField()
    source_feedback = RAGRetrievedChunkFeedbackSerializer(many=True, read_only=True)

    class Meta:
        model = RAGResponseFeedback
        fields = [
            "id",
            "rag_response_id",
            "doctor_email",
            "rating",
            "comment",
            "is_source_grounded",
            "is_clinically_useful",
            "is_safe",
            "needs_admin_review",
            "review_status",
            "reviewed_by_email",
            "reviewed_at",
            "review_notes",
            "source_feedback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_reviewed_by_email(self, obj):
        if obj.reviewed_by_id:
            return obj.reviewed_by.email
        return None


class RAGFeedbackReviewSerializer(serializers.Serializer):
    """Input for staff review of a RAG feedback item."""

    ALLOWED_STATUSES = [
        RAGFeedbackReviewStatus.REVIEWED,
        RAGFeedbackReviewStatus.DISMISSED,
        RAGFeedbackReviewStatus.ESCALATED,
    ]

    review_status = serializers.ChoiceField(choices=ALLOWED_STATUSES)
    review_notes = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


# ---------------------------------------------------------------------------
# Phase 12E — Analytics and export serializers
# ---------------------------------------------------------------------------


class RAGAnalyticsSummarySerializer(serializers.Serializer):
    """
    Read-only serializer that wraps the analytics summary dict returned by
    get_rag_analytics_summary().  Used only for schema documentation purposes.
    """

    feedback = serializers.DictField(read_only=True)
    retrieval_quality = serializers.DictField(read_only=True)
    usage = serializers.DictField(read_only=True)


class RAGDatasetExportSerializer(serializers.Serializer):
    """Input serializer for the admin dataset export endpoint."""

    format = serializers.ChoiceField(choices=["json", "csv"], default="json")
    include_text = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "Include query_text and response_text. "
            "WARNING: may contain clinician-generated free text. "
            "Off by default."
        ),
    )
    anonymize = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Hash doctor/object IDs. On by default.",
    )
