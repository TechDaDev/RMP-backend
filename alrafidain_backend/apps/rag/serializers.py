from django.conf import settings
from rest_framework import serializers

from .models import RAGQuery, RAGResponse, RAGRetrievedChunk


class DoctorRAGQuerySerializer(serializers.Serializer):
    """Input serializer for the general doctor RAG query endpoint."""

    question = serializers.CharField(max_length=2000)
    document_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
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
            raise serializers.ValidationError(
                f"top_k may not exceed {max_k}."
            )
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
