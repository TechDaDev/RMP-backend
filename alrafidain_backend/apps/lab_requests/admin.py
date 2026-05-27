from django.contrib import admin

from .models import LabOrderRequest, LabOrderRequestItem


@admin.register(LabOrderRequest)
class LabOrderRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "lab_order",
        "patient",
        "lab",
        "status",
        "payment_status",
        "payment_intent",
        "paid_at",
        "total_price",
        "currency",
        "created_at",
    ]
    list_filter = ["status", "currency", "created_at"]
    search_fields = [
        "lab_order__id",
        "patient__email",
        "patient__first_name",
        "patient__last_name",
        "lab__user__email",
        "lab__laboratory_name",
    ]
    readonly_fields = ["payment_intent", "paid_at", "payment_failed_at", "refunded_at"]


@admin.register(LabOrderRequestItem)
class LabOrderRequestItemAdmin(admin.ModelAdmin):
    list_display = [
        "request",
        "requested_name_snapshot",
        "quoted_name",
        "offering",
        "availability_status",
        "quantity",
        "unit_price",
        "total_price",
    ]
    list_filter = ["availability_status"]
    search_fields = [
        "requested_name_snapshot",
        "quoted_name",
        "offering__lab_test__name",
        "offering__custom_test_name",
    ]
