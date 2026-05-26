from django.contrib import admin

from .models import (
    LabCompletionRecord,
    LabOrder,
    LabOrderItem,
    LabResult,
    LabResultCorrection,
    LabTestCatalog,
)


@admin.register(LabTestCatalog)
class LabTestCatalogAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category", "code", "is_active", "display_order")
    list_filter = ("category", "is_active", "created_at")
    search_fields = ("name", "code")
    ordering = ("display_order", "name")


class LabOrderItemInline(admin.TabularInline):
    model = LabOrderItem
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "doctor",
        "patient",
        "status",
        "expires_at",
        "fully_completed_at",
        "created_at",
    )
    list_filter = ("status", "created_at", "expires_at", "fully_completed_at")
    search_fields = ("qr_token", "doctor__email", "patient__email")
    readonly_fields = ("id", "qr_token", "qr_token_created_at", "created_at", "updated_at")
    inlines = [LabOrderItemInline]


@admin.register(LabOrderItem)
class LabOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lab_order",
        "get_display_test_name",
        "test_name",
        "lab_test",
        "custom_test_name",
        "category",
        "status",
        "created_at",
    )
    list_filter = ("status", "category", "created_at")
    search_fields = (
        "test_name",
        "custom_test_name",
        "lab_test__name",
        "lab_test__short_name",
        "lab_test__loinc_code",
        "lab_order__doctor__email",
        "lab_order__patient__email",
    )
    readonly_fields = ("id", "get_display_test_name", "created_at", "updated_at")
    raw_id_fields = ("lab_test",)

    @admin.display(description="Display Test Name")
    def get_display_test_name(self, obj):
        return obj.display_test_name


@admin.register(LabCompletionRecord)
class LabCompletionRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "lab_order", "lab_order_item", "laboratorian", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("lab_order__qr_token", "laboratorian__email", "lab_order_item__test_name")
    readonly_fields = ("id", "created_at", "updated_at")


class LabResultCorrectionInline(admin.TabularInline):
    model = LabResultCorrection
    extra = 0
    readonly_fields = (
        "id",
        "corrected_by",
        "previous_data",
        "new_data",
        "reason",
        "created_at",
        "updated_at",
    )
    can_delete = False


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lab_order",
        "lab_order_item",
        "status",
        "value_type",
        "flag",
        "is_linked_to_medical_record",
        "released_at",
        "created_at",
    )
    list_filter = (
        "status",
        "value_type",
        "flag",
        "is_linked_to_medical_record",
        "created_at",
        "released_at",
    )
    search_fields = (
        "patient__email",
        "doctor__email",
        "laboratorian__email",
        "lab_order_item__test_name",
    )
    readonly_fields = (
        "id",
        "submitted_at",
        "reviewed_at",
        "released_at",
        "corrected_at",
        "created_at",
        "updated_at",
    )
    inlines = [LabResultCorrectionInline]


@admin.register(LabResultCorrection)
class LabResultCorrectionAdmin(admin.ModelAdmin):
    list_display = ("id", "lab_result", "corrected_by", "created_at")
    search_fields = (
        "lab_result__patient__email",
        "lab_result__doctor__email",
        "corrected_by__email",
    )
    readonly_fields = ("id", "created_at", "updated_at")
