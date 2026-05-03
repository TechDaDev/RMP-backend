from django.conf import settings
from django.db import models

from apps.common.choices import (
    KnowledgeApprovalStatus,
    KnowledgeAudience,
    KnowledgeDocumentType,
    KnowledgeLanguage,
    KnowledgeProcessingStatus,
    MedicalSpecialty,
)
from apps.common.models import BaseModel
from apps.common.upload_paths import knowledge_document_upload_path


class KnowledgeDocument(BaseModel):
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=50, choices=KnowledgeDocumentType.choices)
    language = models.CharField(max_length=20, choices=KnowledgeLanguage.choices)
    audience = models.CharField(max_length=20, choices=KnowledgeAudience.choices)
    specialty = models.CharField(
        max_length=50,
        choices=MedicalSpecialty.choices,
        blank=True,
        null=True,
    )
    source_authority = models.CharField(max_length=300, blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    file = models.FileField(upload_to=knowledge_document_upload_path)
    original_filename = models.CharField(max_length=500)
    file_size = models.PositiveBigIntegerField(blank=True, null=True)
    mime_type = models.CharField(max_length=100, blank=True, null=True)

    approval_status = models.CharField(
        max_length=20,
        choices=KnowledgeApprovalStatus.choices,
        default=KnowledgeApprovalStatus.PENDING,
    )
    processing_status = models.CharField(
        max_length=20,
        choices=KnowledgeProcessingStatus.choices,
        default=KnowledgeProcessingStatus.UPLOADED,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_knowledge_documents",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_knowledge_documents",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Knowledge Document"
        verbose_name_plural = "Knowledge Documents"

    def __str__(self):
        return self.title


class KnowledgeDocumentText(BaseModel):
    document = models.OneToOneField(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="extracted_text",
    )
    text = models.TextField()
    page_count = models.PositiveIntegerField(blank=True, null=True)
    extraction_metadata = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Knowledge Document Text"
        verbose_name_plural = "Knowledge Document Texts"

    def __str__(self):
        return f"Text for {self.document.title}"


class KnowledgeChunk(BaseModel):
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    page_number = models.PositiveIntegerField(blank=True, null=True)
    section_title = models.CharField(max_length=500, blank=True, null=True)
    token_estimate = models.PositiveIntegerField(blank=True, null=True)
    metadata = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        unique_together = [("document", "chunk_index")]
        verbose_name = "Knowledge Chunk"
        verbose_name_plural = "Knowledge Chunks"

    def __str__(self):
        return f"{self.document.title} — chunk {self.chunk_index}"


class KnowledgeProcessingLog(BaseModel):
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="processing_logs",
    )
    action = models.CharField(max_length=100)
    status = models.CharField(max_length=50)
    message = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Knowledge Processing Log"
        verbose_name_plural = "Knowledge Processing Logs"

    def __str__(self):
        return f"{self.document.title} — {self.action} ({self.status})"
