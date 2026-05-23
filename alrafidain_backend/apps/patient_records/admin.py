from django.conf import settings
from django.contrib import admin, messages

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord, PatientMedicalReport
from .services import classify_medical_report_with_llm


@admin.register(PatientMedicalRecord)
class PatientMedicalRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "created_at", "updated_at")
    search_fields = ("patient__email",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(MedicalRecordEntry)
class MedicalRecordEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "medical_record",
        "category",
        "verification_status",
        "source_role",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "verification_status", "source_role", "is_active", "created_at")
    search_fields = (
        "medical_record__patient__email",
        "title",
        "value",
        "source_user__email",
        "verified_by__email",
    )
    readonly_fields = ("id", "created_at", "updated_at", "verified_at")


@admin.register(BloodGroupRecord)
class BloodGroupRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "medical_record", "blood_group", "verification_status", "updated_at")
    list_filter = ("verification_status", "created_at")
    search_fields = ("medical_record__patient__email", "source_user__email", "verified_by__email")
    readonly_fields = ("id", "created_at", "updated_at", "verified_at")


@admin.register(PatientMedicalReport)
class PatientMedicalReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "consultation",
        "report_type",
        "processing_status",
        "is_medical_report",
        "created_at",
        "processed_at",
        "reviewed_at",
    )
    list_filter = (
        "report_type",
        "processing_status",
        "is_medical_report",
        "visibility",
        "created_at",
    )
    search_fields = (
        "patient__email",
        "title",
        "original_filename",
    )
    readonly_fields = (
        "id",
        "raw_ocr_text",
        "cleaned_report_text",
        "structured_payload",
        "source_attachment",
        "source_message",
        "linked_medical_record_entry",
        "created_at",
        "updated_at",
    )
    actions = ["run_llm_classification"]

    @admin.action(description="Run LLM classification for selected reports")
    def run_llm_classification(self, request, queryset):
        if not bool(getattr(settings, "CLINICAL_REPORT_LLM_ENABLED", False)):
            self.message_user(
                request,
                "LLM classification is disabled in settings.",
                level=messages.WARNING,
            )
            return

        completed = 0
        failed = 0
        for report in queryset:
            try:
                classify_medical_report_with_llm(report=report, request=request, force=True)
                completed += 1
            except Exception:
                failed += 1

        self.message_user(
            request,
            f"LLM classification finished. Completed: {completed}, Failed: {failed}.",
            level=messages.INFO,
        )
