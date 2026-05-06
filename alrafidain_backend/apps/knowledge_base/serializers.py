import os

from rest_framework import serializers

from apps.common.choices import (
    KnowledgeApprovalStatus,
    KnowledgeAudience,
    KnowledgeDocumentType,
    KnowledgeLanguage,
    KnowledgeProcessingStatus,
    MedicalSpecialty,
)

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeProcessingLog

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class KnowledgeProcessingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeProcessingLog
        fields = ["id", "action", "status", "message", "metadata", "created_at"]


class KnowledgeChunkSerializer(serializers.ModelSerializer):
    has_embedding = serializers.BooleanField(read_only=True)

    class Meta:
        model = KnowledgeChunk
        fields = [
            "id",
            "document",
            "chunk_index",
            "text",
            "page_number",
            "section_title",
            "token_estimate",
            "metadata",
            "is_active",
            "has_embedding",
            "embedding_model",
            "embedded_at",
            "created_at",
        ]


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    """Lightweight list serializer."""

    chunk_count = serializers.SerializerMethodField()
    uploaded_by_email = serializers.EmailField(source="uploaded_by.email", read_only=True)

    class Meta:
        model = KnowledgeDocument
        fields = [
            "id",
            "title",
            "document_type",
            "language",
            "audience",
            "specialty",
            "source_authority",
            "version",
            "approval_status",
            "processing_status",
            "is_active",
            "uploaded_by_email",
            "chunk_count",
            "created_at",
            "updated_at",
        ]

    def get_chunk_count(self, obj):
        if hasattr(obj, "chunk_count"):
            return obj.chunk_count
        return obj.chunks.filter(is_active=True).count()


class KnowledgeDocumentDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer including processing logs and chunk count."""

    chunk_count = serializers.SerializerMethodField()
    processing_logs = KnowledgeProcessingLogSerializer(many=True, read_only=True)
    uploaded_by_email = serializers.EmailField(source="uploaded_by.email", read_only=True)
    approved_by_email = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeDocument
        fields = [
            "id",
            "title",
            "document_type",
            "language",
            "audience",
            "specialty",
            "source_authority",
            "version",
            "description",
            "original_filename",
            "file_size",
            "mime_type",
            "approval_status",
            "processing_status",
            "approved_at",
            "rejected_reason",
            "is_active",
            "uploaded_by_email",
            "approved_by_email",
            "chunk_count",
            "processing_logs",
            "created_at",
            "updated_at",
        ]

    def get_chunk_count(self, obj):
        if hasattr(obj, "chunk_count"):
            return obj.chunk_count
        return obj.chunks.filter(is_active=True).count()

    def get_approved_by_email(self, obj):
        return obj.approved_by.email if obj.approved_by else None


class KnowledgeDocumentUploadSerializer(serializers.ModelSerializer):
    """Used to validate and create a new KnowledgeDocument upload."""

    file = serializers.FileField()

    class Meta:
        model = KnowledgeDocument
        fields = [
            "title",
            "document_type",
            "language",
            "audience",
            "specialty",
            "source_authority",
            "version",
            "description",
            "file",
        ]

    def validate_file(self, value):
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}."
            )
        return value

    def create(self, validated_data):
        request = self.context["request"]
        file = validated_data["file"]
        validated_data["uploaded_by"] = request.user
        validated_data["original_filename"] = file.name
        validated_data["file_size"] = file.size
        validated_data["mime_type"] = getattr(file, "content_type", None)
        validated_data["approval_status"] = KnowledgeApprovalStatus.PENDING
        validated_data["processing_status"] = KnowledgeProcessingStatus.UPLOADED
        return super().create(validated_data)


class KnowledgeDocumentApproveSerializer(serializers.Serializer):
    """Empty body — approval has no required input."""

    pass


class KnowledgeDocumentRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=1, max_length=2000)


class KnowledgeDocumentArchiveSerializer(serializers.Serializer):
    """Empty body — archive has no required input."""

    pass


class KnowledgeChunkSearchSerializer(serializers.Serializer):
    q = serializers.CharField(required=True, min_length=1, max_length=500)
    document_type = serializers.ChoiceField(
        choices=KnowledgeDocumentType.choices, required=False, allow_blank=True
    )
    specialty = serializers.ChoiceField(
        choices=MedicalSpecialty.choices, required=False, allow_blank=True
    )
    language = serializers.ChoiceField(
        choices=KnowledgeLanguage.choices, required=False, allow_blank=True
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)


class SemanticSearchSerializer(serializers.Serializer):
    """Input serializer for semantic (vector) search."""

    q = serializers.CharField(required=True, min_length=1, max_length=500)
    document_type = serializers.ChoiceField(
        choices=KnowledgeDocumentType.choices, required=False, allow_blank=True
    )
    specialty = serializers.ChoiceField(
        choices=MedicalSpecialty.choices, required=False, allow_blank=True
    )
    language = serializers.ChoiceField(
        choices=KnowledgeLanguage.choices, required=False, allow_blank=True
    )
    audience = serializers.ChoiceField(
        choices=KnowledgeAudience.choices, required=False, allow_blank=True
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)


class SemanticSearchResultSerializer(serializers.Serializer):
    """Output serializer for a single semantic search hit."""

    chunk_id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    document_type = serializers.CharField()
    language = serializers.CharField()
    text = serializers.CharField()
    chunk_index = serializers.IntegerField()
    score = serializers.FloatField()
    distance = serializers.FloatField()
    rank = serializers.IntegerField()
    embedding_model = serializers.CharField(allow_null=True)
