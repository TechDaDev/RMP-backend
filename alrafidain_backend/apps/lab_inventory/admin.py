from django.contrib import admin

from .models import LabTestOffering


@admin.register(LabTestOffering)
class LabTestOfferingAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "lab",
        "lab_test",
        "custom_test_name",
        "local_name",
        "price",
        "currency",
        "is_available",
        "is_active",
        "estimated_turnaround_time",
        "created_at",
    ]
    search_fields = [
        "lab_test__name",
        "lab_test__short_name",
        "lab_test__loinc_code",
        "custom_test_name",
        "local_name",
        "lab__laboratory_name",
        "lab__user__email",
        "lab__laboratory_license_number",
    ]
    list_filter = [
        "is_available",
        "is_active",
        "currency",
        "lab_test__category",
        "sample_type_override",
    ]
