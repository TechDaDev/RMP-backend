from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.choices import Gender, Governorate, MedicalSpecialty, StaffRole, VerificationStatus
from apps.common.models import BaseModel
from apps.common.upload_paths import (
    doctor_license_upload_path,
    laboratorian_license_upload_path,
    laboratory_license_upload_path,
    national_id_back_upload_path,
    national_id_front_upload_path,
    pharmacist_license_upload_path,
    pharmacy_license_upload_path,
    profile_image_upload_path,
)
from apps.common.validators import iraqi_phone_validator


class UserProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_profile",
    )
    phone_number = models.CharField(max_length=11, blank=True, validators=[iraqi_phone_validator])
    profile_image = models.ImageField(upload_to=profile_image_upload_path, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    governorate = models.CharField(max_length=20, choices=Governorate.choices, blank=True)
    district = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    national_id = models.CharField(max_length=20, blank=True)
    national_id_front_image = models.ImageField(
        upload_to=national_id_front_upload_path,
        blank=True,
        null=True,
    )
    national_id_back_image = models.ImageField(
        upload_to=national_id_back_upload_path,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    _REQUIRED_FIELDS = [
        "phone_number",
        "gender",
        "date_of_birth",
        "governorate",
        "district",
        "national_id_front_image",
        "national_id_back_image",
    ]

    @property
    def is_complete(self) -> bool:
        return bool(all(getattr(self, f) for f in self._REQUIRED_FIELDS))

    @property
    def missing_fields(self) -> list:
        return [f for f in self._REQUIRED_FIELDS if not getattr(self, f)]

    def __str__(self):
        return f"Profile of {self.user.email}"


class PatientProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )
    social_security_id = models.CharField(max_length=30, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=11, blank=True, validators=[iraqi_phone_validator]
    )

    class Meta:
        verbose_name = "Patient Profile"
        verbose_name_plural = "Patient Profiles"

    _REQUIRED_FIELDS = ["emergency_contact_name", "emergency_contact_phone"]

    @property
    def is_complete(self) -> bool:
        return bool(all(getattr(self, f) for f in self._REQUIRED_FIELDS))

    @property
    def missing_fields(self) -> list:
        return [f for f in self._REQUIRED_FIELDS if not getattr(self, f)]

    def __str__(self):
        return f"Patient: {self.user.email}"


class DoctorProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    medical_license_number = models.CharField(max_length=50, blank=True)
    medical_license_image = models.ImageField(
        upload_to=doctor_license_upload_path, blank=True, null=True
    )
    specialty = models.CharField(
        max_length=50,
        choices=MedicalSpecialty.choices,
        blank=True,
    )
    specialty_other = models.CharField(max_length=150, blank=True)
    subspecialty = models.CharField(max_length=100, blank=True)
    professional_title = models.CharField(max_length=100, blank=True)
    years_of_experience = models.PositiveIntegerField(
        blank=True, null=True, validators=[MinValueValidator(0)]
    )
    consultation_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    consultation_currency = models.CharField(max_length=10, default="IQD")
    bio = models.TextField(blank=True)
    work_address = models.TextField(blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_profiles_verified",
    )
    verification_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Doctor Profile"
        verbose_name_plural = "Doctor Profiles"

    _REQUIRED_FIELDS = ["medical_license_number", "medical_license_image", "specialty"]

    @property
    def is_complete(self) -> bool:
        return bool(self.medical_license_number and self.medical_license_image and self.specialty)

    @property
    def missing_fields(self) -> list:
        result = []
        if not self.medical_license_number:
            result.append("medical_license_number")
        if not self.medical_license_image:
            result.append("medical_license_image")
        if not self.specialty:
            result.append("specialty")
        return result

    def clean(self):
        if self.specialty == MedicalSpecialty.OTHER and not self.specialty_other:
            raise ValidationError(
                {"specialty_other": "This field is required when specialty is Other."}
            )
        if self.specialty != MedicalSpecialty.OTHER:
            self.specialty_other = ""

    def __str__(self):
        return f"Doctor: {self.user.email}"


class PharmacistProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pharmacist_profile",
    )
    pharmacist_license_number = models.CharField(max_length=50, blank=True)
    pharmacist_license_image = models.ImageField(
        upload_to=pharmacist_license_upload_path, blank=True, null=True
    )
    pharmacy_name = models.CharField(max_length=200, blank=True)
    pharmacy_license_number = models.CharField(max_length=50, blank=True)
    pharmacy_license_image = models.ImageField(
        upload_to=pharmacy_license_upload_path, blank=True, null=True
    )
    pharmacy_address = models.TextField(blank=True)
    working_hours = models.CharField(max_length=100, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacist_profiles_verified",
    )
    verification_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Pharmacist Profile"
        verbose_name_plural = "Pharmacist Profiles"

    @property
    def is_complete(self) -> bool:
        return bool(
            self.pharmacist_license_number
            and self.pharmacist_license_image
            and self.pharmacy_name
            and self.pharmacy_address
        )

    @property
    def missing_fields(self) -> list:
        result = []
        for field in [
            "pharmacist_license_number",
            "pharmacist_license_image",
            "pharmacy_name",
            "pharmacy_address",
        ]:
            if not getattr(self, field):
                result.append(field)
        return result

    def __str__(self):
        return f"Pharmacist: {self.user.email}"


class LaboratorianProfile(BaseModel):
    WORKING_DAY_CHOICES = [
        "saturday",
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="laboratorian_profile",
    )
    laboratorian_license_number = models.CharField(max_length=50, blank=True)
    laboratorian_license_image = models.ImageField(
        upload_to=laboratorian_license_upload_path, blank=True, null=True
    )
    laboratory_name = models.CharField(max_length=200, blank=True)
    laboratory_license_number = models.CharField(max_length=50, blank=True)
    laboratory_license_image = models.ImageField(
        upload_to=laboratory_license_upload_path, blank=True, null=True
    )
    laboratory_address = models.TextField(blank=True)
    laboratory_governorate = models.CharField(max_length=20, choices=Governorate.choices, blank=True)
    laboratory_phone_number = models.CharField(
        max_length=11,
        blank=True,
        validators=[iraqi_phone_validator],
    )
    specialization = models.CharField(max_length=100, blank=True)
    working_hours = models.CharField(max_length=100, blank=True)
    working_days = models.JSONField(default=list, blank=True)
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="laboratorian_profiles_verified",
    )
    verification_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Laboratorian Profile"
        verbose_name_plural = "Laboratorian Profiles"

    @property
    def is_complete(self) -> bool:
        return bool(
            self.laboratorian_license_number
            and self.laboratorian_license_image
            and self.laboratory_name
            and self.laboratory_address
        )

    @property
    def missing_fields(self) -> list:
        result = []
        for field in [
            "laboratorian_license_number",
            "laboratorian_license_image",
            "laboratory_name",
            "laboratory_address",
        ]:
            if not getattr(self, field):
                result.append(field)
        return result

    @property
    def is_open_now(self) -> bool:
        if not self.working_days or not self.opening_time or not self.closing_time:
            return False

        now = timezone.localtime()
        current_day = now.strftime("%A").lower()
        if current_day not in self.working_days:
            return False

        current_time = now.time()
        if self.opening_time <= self.closing_time:
            return self.opening_time <= current_time <= self.closing_time

        # Overnight shift (e.g. 20:00 -> 04:00)
        return current_time >= self.opening_time or current_time <= self.closing_time

    def __str__(self):
        return f"Laboratorian: {self.user.email}"


class StaffProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    staff_role = models.CharField(
        max_length=50,
        choices=StaffRole.choices,
    )
    department = models.CharField(max_length=100, blank=True)

    # Organizational hierarchy
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_supervised",
    )

    # Granular permissions
    can_approve_professionals = models.BooleanField(default=False)
    can_manage_knowledge_base = models.BooleanField(default=False)
    can_export_datasets = models.BooleanField(default=False)
    can_view_audit_logs = models.BooleanField(default=False)

    # Tracking
    hire_date = models.DateField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    deactivation_reason = models.TextField(blank=True)

    # Training / Onboarding
    has_completed_training = models.BooleanField(default=False)
    training_completed_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Staff Profile"
        verbose_name_plural = "Staff Profiles"

    def __str__(self):
        return f"Staff [{self.get_staff_role_display()}]: {self.user.email}"

