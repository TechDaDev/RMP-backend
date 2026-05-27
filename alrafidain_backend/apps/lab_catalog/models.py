import uuid

from django.conf import settings
from django.db import models


class LabTest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    short_name = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    loinc_code = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=150, blank=True, null=True)
    component = models.CharField(max_length=255, blank=True, null=True)
    system = models.CharField(max_length=150, blank=True, null=True)
    sample_type = models.CharField(max_length=150, blank=True, null=True)
    units = models.CharField(max_length=100, blank=True, null=True)
    source_name = models.CharField(max_length=100, default="manual")
    source_code = models.CharField(max_length=100, blank=True, null=True)
    source_version = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.short_name and self.name and self.short_name != self.name:
            return f"{self.short_name} - {self.name}"
        return self.name


class LabTestAlias(models.Model):
    class AliasType(models.TextChoices):
        SHORT_NAME = "short_name", "Short Name"
        SYNONYM = "synonym", "Synonym"
        LOCAL = "local", "Local"
        ARABIC = "arabic", "Arabic"
        MISSPELLING = "misspelling", "Misspelling"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab_test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255, db_index=True)
    alias_type = models.CharField(max_length=20, choices=AliasType.choices)
    language = models.CharField(max_length=20, default="en")
    source_name = models.CharField(max_length=100, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["alias"]

    def __str__(self):
        return f"{self.alias} ({self.alias_type})"


class LabTestClinicalInfo(models.Model):
    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab_test = models.OneToOneField(LabTest, on_delete=models.CASCADE, related_name="clinical_info")
    purpose_summary = models.TextField(blank=True, null=True)
    patient_preparation = models.TextField(blank=True, null=True)
    specimen_type = models.CharField(max_length=255, blank=True, null=True)
    sample_collection_notes = models.TextField(blank=True, null=True)
    clinical_significance = models.TextField(blank=True, null=True)
    interpretation_summary = models.TextField(blank=True, null=True)
    interfering_factors = models.TextField(blank=True, null=True)
    safety_notes = models.TextField(blank=True, null=True)
    patient_explanation = models.TextField(blank=True, null=True)
    provider_notes = models.TextField(blank=True, null=True)
    source_name = models.CharField(max_length=255, blank=True, null=True)
    source_type = models.CharField(max_length=50, default="manual")
    source_document_id = models.CharField(max_length=255, blank=True, null=True)
    source_chunk_ids = models.JSONField(default=list, blank=True)
    source_page_numbers = models.JSONField(default=list, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.DRAFT,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_lab_clinical_infos",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ClinicalInfo for {self.lab_test}"


class LabCatalogImportBatch(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_name = models.CharField(max_length=100)
    source_version = models.CharField(max_length=100, blank=True, null=True)
    imported_file = models.CharField(max_length=255, blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    total_records = models.PositiveIntegerField(default=0)
    created_records = models.PositiveIntegerField(default=0)
    updated_records = models.PositiveIntegerField(default=0)
    skipped_records = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source_name} lab import ({self.status})"
