from django.contrib import admin

from .models import LabCatalogImportBatch, LabTest, LabTestAlias, LabTestClinicalInfo


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "name",
        "short_name",
        "loinc_code",
        "category",
        "sample_type",
        "source_name",
        "is_active",
        "is_verified",
    ]
    search_fields = ["name", "short_name", "loinc_code", "aliases__alias"]
    list_filter = ["category", "sample_type", "source_name", "is_active", "is_verified"]


@admin.register(LabTestAlias)
class LabTestAliasAdmin(admin.ModelAdmin):
    list_display = ["alias", "lab_test", "alias_type", "language", "source_name"]
    search_fields = ["alias", "lab_test__name", "lab_test__short_name"]
    list_filter = ["alias_type", "language", "source_name"]


@admin.register(LabTestClinicalInfo)
class LabTestClinicalInfoAdmin(admin.ModelAdmin):
    list_display = [
        "lab_test",
        "review_status",
        "source_name",
        "source_type",
        "reviewed_by",
        "reviewed_at",
    ]
    search_fields = ["lab_test__name", "lab_test__short_name", "purpose_summary", "clinical_significance"]
    list_filter = ["review_status", "source_type", "source_name"]


@admin.register(LabCatalogImportBatch)
class LabCatalogImportBatchAdmin(admin.ModelAdmin):
    list_display = [
        "source_name",
        "source_version",
        "status",
        "total_records",
        "created_records",
        "updated_records",
        "skipped_records",
        "started_at",
        "finished_at",
    ]
    list_filter = ["source_name", "status"]
