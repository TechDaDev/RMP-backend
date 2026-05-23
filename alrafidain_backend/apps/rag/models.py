from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.choices import (
    DoctorAIAssistantMessageStatus,
    DoctorAIAssistantSafetyLevel,
    DoctorAIAssistantTriggerType,
    RAGFeedbackRating,
    RAGFeedbackReviewStatus,
    RAGResponseStatus,
    RAGSafetyLevel,
    RAGServiceContext,
    RAGSourceRelevance,
)
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
        indexes = [
            models.Index(fields=["requested_by", "-created_at"]),
            models.Index(fields=["service_context", "-created_at"]),
            models.Index(fields=["service_context", "object_id", "-created_at"]),
        ]

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
        indexes = [
            models.Index(fields=["rag_query", "rank"]),
            models.Index(fields=["chunk", "-created_at"]),
        ]

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


class DoctorAIAssistantMessage(BaseModel):
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="doctor_ai_messages",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doctor_ai_assistant_messages",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="patient_ai_case_messages",
    )
    trigger_type = models.CharField(
        max_length=40,
        choices=DoctorAIAssistantTriggerType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=DoctorAIAssistantMessageStatus.choices,
        default=DoctorAIAssistantMessageStatus.UNREAD,
    )
    safety_level = models.CharField(
        max_length=20,
        choices=DoctorAIAssistantSafetyLevel.choices,
        default=DoctorAIAssistantSafetyLevel.DOCTOR_ONLY,
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    summary = models.JSONField(default=dict, blank=True)
    source_report = models.ForeignKey(
        "patient_records.PatientMedicalReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_ai_messages",
    )
    source_rag_response = models.ForeignKey(
        "RAGResponse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_ai_messages",
    )
    source_medical_record_entry = models.ForeignKey(
        "patient_records.MedicalRecordEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_ai_messages",
    )
    source_metadata = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["consultation", "doctor", "-created_at"]),
            models.Index(fields=["doctor", "status", "-created_at"]),
            models.Index(fields=["source_report"]),
            models.Index(fields=["source_rag_response"]),
            models.Index(fields=["trigger_type", "-created_at"]),
        ]

    def clean(self):
        from apps.common.choices import RAGServiceContext, UserType

        if not (self.body or "").strip():
            raise ValidationError({"body": "Assistant message body cannot be empty."})

        if (
            self.consultation_id
            and self.patient_id
            and self.consultation.patient_id != self.patient_id
        ):
            raise ValidationError(
                {"patient": "Consultation patient must match assistant message patient."}
            )

        if (
            self.consultation_id
            and self.doctor_id
            and self.consultation.assigned_doctor_id != self.doctor_id
        ):
            raise ValidationError(
                {"doctor": "Doctor must be the assigned doctor for this consultation."}
            )

        if self.doctor_id and self.doctor.user_type != UserType.DOCTOR:
            raise ValidationError({"doctor": "Doctor AI message owner must be a doctor user."})

        if self.patient_id and self.patient.user_type != UserType.PATIENT:
            raise ValidationError({"patient": "Doctor AI message patient must be a patient user."})

        if self.source_report_id:
            if self.source_report.patient_id != self.patient_id:
                raise ValidationError(
                    {"source_report": "Source report patient must match assistant message patient."}
                )
            if (
                self.source_report.consultation_id
                and self.source_report.consultation_id != self.consultation_id
            ):
                raise ValidationError(
                    {
                        "source_report": (
                            "Source report consultation must match assistant consultation."
                        )
                    }
                )

        if self.source_rag_response_id and self.source_report_id:
            rag_query = self.source_rag_response.rag_query
            if (
                rag_query.service_context == RAGServiceContext.REPORT_CASE_UPDATE
                and rag_query.object_id
                and str(rag_query.object_id) != str(self.source_report_id)
            ):
                raise ValidationError(
                    {
                        "source_rag_response": (
                            "For report_case_update responses, rag object_id must "
                            "match source report."
                        )
                    }
                )

    def __str__(self):
        return f"AI assistant message for consultation {self.consultation_id}"


class RAGResponseFeedback(BaseModel):
    """Doctor-submitted feedback on a single RAG response."""

    rag_response = models.OneToOneField(
        RAGResponse,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rag_feedbacks",
    )
    rating = models.CharField(
        max_length=25,
        choices=RAGFeedbackRating.choices,
    )
    comment = models.TextField(blank=True, null=True)
    is_source_grounded = models.BooleanField(null=True, blank=True)
    is_clinically_useful = models.BooleanField(null=True, blank=True)
    is_safe = models.BooleanField(default=True)
    needs_admin_review = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=20,
        choices=RAGFeedbackReviewStatus.choices,
        default=RAGFeedbackReviewStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_rag_feedbacks",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "RAG Response Feedback"
        verbose_name_plural = "RAG Response Feedbacks"
        indexes = [
            models.Index(fields=["doctor", "-created_at"]),
            models.Index(fields=["review_status", "-created_at"]),
            models.Index(fields=["needs_admin_review", "-created_at"]),
            models.Index(fields=["rating", "-created_at"]),
        ]

    def __str__(self):
        return f"RAGFeedback {self.id} [{self.rating}] by {self.doctor_id}"

    def save(self, *args, **kwargs):
        # Enforce safety escalation rules
        if self.rating == RAGFeedbackRating.UNSAFE:
            self.is_safe = False
        if not self.is_safe:
            self.needs_admin_review = True
        super().save(*args, **kwargs)


class RAGRetrievedChunkFeedback(BaseModel):
    """Per-source relevance feedback for a single retrieved chunk."""

    feedback = models.ForeignKey(
        RAGResponseFeedback,
        on_delete=models.CASCADE,
        related_name="source_feedback",
    )
    retrieved_chunk = models.ForeignKey(
        RAGRetrievedChunk,
        on_delete=models.CASCADE,
        related_name="feedback_items",
    )
    relevance = models.CharField(
        max_length=25,
        choices=RAGSourceRelevance.choices,
        default=RAGSourceRelevance.UNKNOWN,
    )
    comment = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["feedback", "retrieved_chunk__rank"]
        unique_together = [("feedback", "retrieved_chunk")]
        verbose_name = "RAG Retrieved Chunk Feedback"
        verbose_name_plural = "RAG Retrieved Chunk Feedbacks"
        indexes = [
            models.Index(fields=["feedback", "retrieved_chunk"]),
        ]

    def __str__(self):
        return f"ChunkFeedback [{self.relevance}] for chunk {self.retrieved_chunk_id}"
