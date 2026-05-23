from django.contrib import admin

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord, PatientMedicalReport


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
