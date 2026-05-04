from django.conf import settings
from django.db import models

from apps.common.choices import RAGResponseStatus, RAGSafetyLevel, RAGServiceContext
from apps.common.models import BaseModel


class RAGQuery(BaseModel):
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rag_queries",
    )
    service_context = models.CharField(
        max_length=30,
        choices=RAGServiceContext.choices,
    )
    object_id = models.UUIDField(null=True, blank=True)
    query_text = models.TextField()
    role_context = models.CharField(max_length=50, default="doctor")
    top_k = models.PositiveSmallIntegerField(default=6)
    filters = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "RAG Query"
        verbose_name_plural = "RAG Queries"

    def __str__(self):
        return f"RAGQuery {self.id} [{self.service_context}] by {self.requested_by_id}"


class RAGRetrievedChunk(BaseModel):
    rag_query = models.ForeignKey(
        RAGQuery,
        on_delete=models.CASCADE,
        related_name="retrieved_chunks",
    )
    chunk = models.ForeignKey(
        "knowledge_base.KnowledgeChunk",
        on_delete=models.PROTECT,
        related_name="rag_retrievals",
    )
    rank = models.PositiveIntegerField()
    score = models.FloatField()
    distance = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["rag_query", "rank"]
        verbose_name = "RAG Retrieved Chunk"
        verbose_name_plural = "RAG Retrieved Chunks"

    def __str__(self):
        return f"RAGChunk rank={self.rank} score={self.score:.4f}"


class RAGResponse(BaseModel):
    rag_query = models.OneToOneField(
        RAGQuery,
        on_delete=models.CASCADE,
        related_name="response",
    )
    response_text = models.TextField()
    provider = models.CharField(max_length=50, default="deepseek")
    model_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=RAGResponseStatus.choices,
    )
    safety_level = models.CharField(
        max_length=20,
        choices=RAGSafetyLevel.choices,
        default=RAGSafetyLevel.DOCTOR_ONLY,
    )
    doctor_review_required = models.BooleanField(default=True)
    patient_visible = models.BooleanField(default=False)
    prompt_text = models.TextField(blank=True, null=True)
    raw_response = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, null=True)
    token_input = models.PositiveIntegerField(null=True, blank=True)
    token_output = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "RAG Response"
        verbose_name_plural = "RAG Responses"

    def __str__(self):
        return f"RAGResponse {self.id} [{self.status}]"

    def save(self, *args, **kwargs):
        # Enforce safety invariants — patient_visible must always be False in Phase 12C
        self.patient_visible = False
        self.doctor_review_required = True
        super().save(*args, **kwargs)
