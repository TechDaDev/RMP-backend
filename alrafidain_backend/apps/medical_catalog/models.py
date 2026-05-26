import uuid

from django.db import models


class Drug(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    generic_name = models.CharField(max_length=255, blank=True, null=True)
    brand_name = models.CharField(max_length=255, blank=True, null=True)
    form = models.CharField(max_length=100, blank=True, null=True)
    strength = models.CharField(max_length=100, blank=True, null=True)
    route = models.CharField(max_length=100, blank=True, null=True)
    rxnorm_rxcui = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    atc_code = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    warnings = models.TextField(blank=True, null=True)
    contraindications = models.TextField(blank=True, null=True)
    dosage_info = models.TextField(blank=True, null=True)
    adverse_reactions = models.TextField(blank=True, null=True)
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
        parts = [self.name]
        if self.strength:
            parts.append(self.strength)
        if self.form:
            parts.append(self.form)
        return " ".join(parts)


class DrugAlias(models.Model):
    class AliasType(models.TextChoices):
        GENERIC = "generic", "Generic"
        BRAND = "brand", "Brand"
        SYNONYM = "synonym", "Synonym"
        LOCAL = "local", "Local"
        ARABIC = "arabic", "Arabic"
        MISSPELLING = "misspelling", "Misspelling"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255, db_index=True)
    alias_type = models.CharField(max_length=20, choices=AliasType.choices)
    language = models.CharField(max_length=20, default="en")
    source_name = models.CharField(max_length=100, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["alias"]

    def __str__(self):
        return f"{self.alias} ({self.alias_type})"


class CatalogImportBatch(models.Model):
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
        return f"{self.source_name} import ({self.status})"
