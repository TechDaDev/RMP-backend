from django.contrib import admin

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentText, KnowledgeProcessingLog


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "document_type",
        "language",
        "audience",
        "specialty",
        "approval_status",
        "processing_status",
        "is_active",
        "uploaded_by",
        "created_at",
    ]
    list_filter = [
        "document_type",
        "language",
        "audience",
        "specialty",
        "approval_status",
        "processing_status",
        "is_active",
        "created_at",
    ]
    search_fields = ["title", "original_filename", "source_authority", "description"]
    readonly_fields = [
        "id",
        "uploaded_by",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    ]
    raw_id_fields = ["uploaded_by", "approved_by"]


@admin.register(KnowledgeDocumentText)
class KnowledgeDocumentTextAdmin(admin.ModelAdmin):
    list_display = ["document", "page_count", "created_at"]
    search_fields = ["document__title"]
    readonly_fields = ["id", "document", "created_at", "updated_at"]


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "chunk_index", "token_estimate", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["document__title", "text"]
    readonly_fields = ["id", "document", "chunk_index", "created_at", "updated_at"]


@admin.register(KnowledgeProcessingLog)
class KnowledgeProcessingLogAdmin(admin.ModelAdmin):
    list_display = ["document", "action", "status", "created_at"]
    list_filter = ["action", "status", "created_at"]
    search_fields = ["document__title", "message"]
    readonly_fields = [
        "id",
        "document",
        "action",
        "status",
        "message",
        "metadata",
        "created_at",
        "updated_at",
    ]
