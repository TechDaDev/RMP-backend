from django.contrib import admin

from .models import PharmacyDrugInventory


@admin.register(PharmacyDrugInventory)
class PharmacyDrugInventoryAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "pharmacy",
        "drug",
        "custom_drug_name",
        "brand_name",
        "strength",
        "form",
        "price",
        "currency",
        "stock_status",
        "quantity",
        "is_available",
        "is_active",
    ]
    search_fields = [
        "drug__name",
        "drug__generic_name",
        "drug__brand_name",
        "custom_drug_name",
        "brand_name",
    ]
    list_filter = ["stock_status", "is_available", "is_active", "currency", "form", "route"]
