from django.contrib import admin

from .models import PharmacyPrescriptionRequest, PharmacyPrescriptionRequestItem


@admin.register(PharmacyPrescriptionRequest)
class PharmacyPrescriptionRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "prescription",
        "patient",
        "pharmacy",
        "status",
        "total_price",
        "currency",
        "created_at",
    ]
    list_filter = ["status", "currency", "created_at"]
    search_fields = [
        "prescription__id",
        "patient__email",
        "patient__first_name",
        "patient__last_name",
        "pharmacy__user__email",
        "pharmacy__pharmacy_name",
    ]


@admin.register(PharmacyPrescriptionRequestItem)
class PharmacyPrescriptionRequestItemAdmin(admin.ModelAdmin):
    list_display = [
        "request",
        "requested_name_snapshot",
        "quoted_name",
        "inventory_item",
        "availability_status",
        "quantity",
        "unit_price",
        "total_price",
    ]
    list_filter = ["availability_status"]
    search_fields = [
        "requested_name_snapshot",
        "quoted_name",
        "inventory_item__drug__name",
        "inventory_item__custom_drug_name",
    ]
