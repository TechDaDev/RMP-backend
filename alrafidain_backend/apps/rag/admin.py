from django.contrib import admin

from .models import RAGQuery, RAGResponse, RAGRetrievedChunk


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
        "id", "rag_query", "status", "safety_level",
        "doctor_review_required", "patient_visible",
        "model_name", "token_input", "token_output", "created_at",
    ]
    list_filter = ["status", "safety_level", "provider"]
    search_fields = ["response_text", "rag_query__query_text"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]
