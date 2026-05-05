from django.contrib import admin

from .models import DispensingRecord, Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at", "dispensed_at", "cancelled_at")


class DispensingRecordInline(admin.TabularInline):
    model = DispensingRecord
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "doctor",
        "status",
        "created_at",
        "expires_at",
        "fully_dispensed_at",
    )
    list_filter = ("status", "created_at", "expires_at", "fully_dispensed_at")
    search_fields = ("qr_token", "doctor__email", "patient__email")
    readonly_fields = ("id", "qr_token", "qr_token_created_at", "created_at", "updated_at")
    inlines = [PrescriptionItemInline, DispensingRecordInline]


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ("id", "prescription", "medication_name", "status", "created_at")
    list_filter = ("status", "route")
    search_fields = ("medication_name", "prescription__qr_token", "prescription__patient__email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(DispensingRecord)
class DispensingRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "prescription", "prescription_item", "pharmacist", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("pharmacist__email", "prescription__qr_token")
    readonly_fields = ("id", "created_at", "updated_at")
