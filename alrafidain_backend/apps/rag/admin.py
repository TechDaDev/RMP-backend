from django.contrib import admin

from .models import (
    DoctorAIAssistantMessage,
    RAGQuery,
    RAGResponse,
    RAGResponseFeedback,
    RAGRetrievedChunk,
    RAGRetrievedChunkFeedback,
)


@admin.register(RAGQuery)
class RAGQueryAdmin(admin.ModelAdmin):
    list_display = ["id", "requested_by", "service_context", "top_k", "created_at"]
    list_filter = ["service_context"]
    search_fields = ["query_text", "requested_by__email"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(RAGRetrievedChunk)
class RAGRetrievedChunkAdmin(admin.ModelAdmin):
    list_display = ["id", "rag_query", "chunk", "rank", "score", "created_at"]
    list_filter = ["rag_query__service_context"]
    search_fields = ["rag_query__query_text"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["rag_query", "rank"]


@admin.register(RAGResponse)
class RAGResponseAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "rag_query",
        "status",
        "safety_level",
        "doctor_review_required",
        "patient_visible",
        "model_name",
        "token_input",
        "token_output",
        "created_at",
    ]
    list_filter = ["status", "safety_level", "provider"]
    search_fields = ["response_text", "rag_query__query_text"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]


class RAGRetrievedChunkFeedbackInline(admin.TabularInline):
    model = RAGRetrievedChunkFeedback
    extra = 0
    readonly_fields = ["id", "retrieved_chunk", "relevance", "comment", "created_at"]
    can_delete = False


@admin.register(RAGResponseFeedback)
class RAGResponseFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "doctor",
        "rag_response",
        "rating",
        "is_safe",
        "needs_admin_review",
        "review_status",
        "reviewed_by",
        "created_at",
    ]
    list_filter = ["rating", "is_safe", "needs_admin_review", "review_status", "created_at"]
    search_fields = [
        "doctor__email",
        "comment",
        "review_notes",
        "rag_response__response_text",
    ]
    readonly_fields = [
        "id",
        "rag_response",
        "doctor",
        "rating",
        "is_safe",
        "needs_admin_review",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]
    inlines = [RAGRetrievedChunkFeedbackInline]


@admin.register(RAGRetrievedChunkFeedback)
class RAGRetrievedChunkFeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "feedback", "retrieved_chunk", "relevance", "created_at"]
    list_filter = ["relevance"]
    search_fields = ["feedback__doctor__email", "comment"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(DoctorAIAssistantMessage)
class DoctorAIAssistantMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "consultation",
        "doctor",
        "patient",
        "trigger_type",
        "status",
        "safety_level",
        "created_at",
    ]
    list_filter = ["trigger_type", "status", "safety_level", "created_at"]
    search_fields = [
        "title",
        "body",
        "doctor__email",
        "patient__email",
        "consultation__id",
    ]
    readonly_fields = ["id", "created_at", "updated_at", "read_at", "archived_at"]
    ordering = ["-created_at"]
