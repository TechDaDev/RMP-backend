"""
Management command: seed_demo_users

Creates demo users for local development and testing.
IMPORTANT: These credentials must never be used in production.

Demo accounts:
    patient@example.com      / DemoPass123!
    doctor@example.com       / DemoPass123!
    pharmacist@example.com   / DemoPass123!
    laboratorian@example.com / DemoPass123!
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.choices import MedicalSpecialty, UserType, VerificationStatus
from apps.patient_records.services import get_or_create_patient_medical_record
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)

User = get_user_model()

DEMO_PASSWORD = "DemoPass123!"

DEMO_USERS = [
    {
        "email": "patient@example.com",
        "user_type": UserType.PATIENT,
        "first_name": "Demo",
        "last_name": "Patient",
    },
    {
        "email": "doctor@example.com",
        "user_type": UserType.DOCTOR,
        "first_name": "Demo",
        "last_name": "Doctor",
    },
    {
        "email": "pharmacist@example.com",
        "user_type": UserType.PHARMACIST,
        "first_name": "Demo",
        "last_name": "Pharmacist",
    },
    {
        "email": "laboratorian@example.com",
        "user_type": UserType.LABORATORIAN,
        "first_name": "Demo",
        "last_name": "Laboratorian",
    },
]


def _get_or_create_user(email, user_type, first_name, last_name):
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "user_type": user_type,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": True,
        },
    )
    if created:
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
    elif not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    return user, created


def _ensure_user_profile(user):
    UserProfile.objects.get_or_create(user=user)


def _seed_patient(user):
    _ensure_user_profile(user)
    PatientProfile.objects.get_or_create(user=user)
    get_or_create_patient_medical_record(user)


def _seed_doctor(user):
    _ensure_user_profile(user)
    profile, _ = DoctorProfile.objects.get_or_create(user=user)
    if not profile.medical_license_number:
        profile.medical_license_number = "DEMO-DOC-001"
        profile.specialty = MedicalSpecialty.INTERNAL_MEDICINE
        profile.verification_status = VerificationStatus.APPROVED
        profile.verified_at = timezone.now()
        profile.save(update_fields=[
            "medical_license_number", "specialty",
            "verification_status", "verified_at",
        ])


def _seed_pharmacist(user):
    _ensure_user_profile(user)
    profile, _ = PharmacistProfile.objects.get_or_create(user=user)
    if not profile.pharmacist_license_number:
        profile.pharmacist_license_number = "DEMO-PH-001"
        profile.pharmacy_name = "Demo Pharmacy"
        profile.pharmacy_license_number = "DEMO-PHL-001"
        profile.pharmacy_address = "123 Demo Street, Baghdad"
        profile.verification_status = VerificationStatus.APPROVED
        profile.verified_at = timezone.now()
        profile.save(update_fields=[
            "pharmacist_license_number", "pharmacy_name",
            "pharmacy_license_number", "pharmacy_address",
            "verification_status", "verified_at",
        ])


def _seed_laboratorian(user):
    _ensure_user_profile(user)
    profile, _ = LaboratorianProfile.objects.get_or_create(user=user)
    if not profile.laboratorian_license_number:
        profile.laboratorian_license_number = "DEMO-LAB-001"
        profile.laboratory_name = "Demo Laboratory"
        profile.laboratory_license_number = "DEMO-LABL-001"
        profile.laboratory_address = "456 Demo Ave, Baghdad"
        profile.verification_status = VerificationStatus.APPROVED
        profile.verified_at = timezone.now()
        profile.save(update_fields=[
            "laboratorian_license_number", "laboratory_name",
            "laboratory_license_number", "laboratory_address",
            "verification_status", "verified_at",
        ])


_SEEDERS = {
    UserType.PATIENT: _seed_patient,
    UserType.DOCTOR: _seed_doctor,
    UserType.PHARMACIST: _seed_pharmacist,
    UserType.LABORATORIAN: _seed_laboratorian,
}


class Command(BaseCommand):
    help = "Create demo users for local development. DO NOT use in production."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "WARNING: Demo users are for DEVELOPMENT only. Never run this in production."
        ))
        created_count = 0
        for spec in DEMO_USERS:
            user, created = _get_or_create_user(
                spec["email"], spec["user_type"], spec["first_name"], spec["last_name"]
            )
            _SEEDERS[spec["user_type"]](user)
            status = "created" if created else "already exists"
            self.stdout.write(f"  {spec['email']} ({spec['user_type']}) — {status}")
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"seed_demo_users done: {created_count} new users created."
        ))
        self.stdout.write("")
        self.stdout.write("Demo credentials (development only):")
        for spec in DEMO_USERS:
            self.stdout.write(f"  {spec['email']}  /  {DEMO_PASSWORD}")
