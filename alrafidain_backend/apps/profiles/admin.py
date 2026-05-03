from django.contrib import admin

from .models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "gender", "governorate", "phone_number", "created_at"]
    list_filter = ["gender", "governorate", "created_at"]
    search_fields = ["user__email", "phone_number", "national_id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "emergency_contact_name", "emergency_contact_phone", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "social_security_id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "specialty", "verification_status", "verified_at", "created_at"]
    list_filter = ["verification_status", "created_at"]
    search_fields = ["user__email", "medical_license_number", "specialty", "specialty_other"]
    readonly_fields = ["created_at", "updated_at"]
    fields = [
        "user",
        "medical_license_number",
        "medical_license_image",
        "specialty",
        "specialty_other",
        "subspecialty",
        "professional_title",
        "years_of_experience",
        "bio",
        "work_address",
        "verification_status",
        "verified_at",
        "verification_notes",
        "created_at",
        "updated_at",
    ]


@admin.register(PharmacistProfile)
class PharmacistProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "pharmacy_name", "verification_status", "verified_at", "created_at"]
    list_filter = ["verification_status", "created_at"]
    search_fields = ["user__email", "pharmacist_license_number", "pharmacy_name"]
    readonly_fields = ["created_at", "updated_at"]
    fields = [
        "user",
        "pharmacist_license_number",
        "pharmacist_license_image",
        "pharmacy_name",
        "pharmacy_license_number",
        "pharmacy_license_image",
        "pharmacy_address",
        "working_hours",
        "verification_status",
        "verified_at",
        "verification_notes",
        "created_at",
        "updated_at",
    ]


@admin.register(LaboratorianProfile)
class LaboratorianProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "laboratory_name", "verification_status", "verified_at", "created_at"]
    list_filter = ["verification_status", "created_at"]
    search_fields = ["user__email", "laboratorian_license_number", "laboratory_name"]
    readonly_fields = ["created_at", "updated_at"]
    fields = [
        "user",
        "laboratorian_license_number",
        "laboratorian_license_image",
        "laboratory_name",
        "laboratory_license_number",
        "laboratory_license_image",
        "laboratory_address",
        "specialization",
        "working_hours",
        "verification_status",
        "verified_at",
        "verification_notes",
        "created_at",
        "updated_at",
    ]

