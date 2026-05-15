"""
Management command: seed_test_users
Creates one test user per role plus a Django superuser for local/Postman testing.
Idempotent — safe to run multiple times; existing users are skipped.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.choices import MedicalSpecialty, StaffRole, UserType, VerificationStatus
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    StaffProfile,
    UserProfile,
)

User = get_user_model()

USERS = [
    {
        "email": "admin@rmp.local",
        "password": "Admin1234!",
        "first_name": "Admin",
        "last_name": "User",
        "user_type": UserType.STAFF,  # Changed from DOCTOR to STAFF
        "is_active": True,
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "email": "patient@rmp.local",
        "password": "Patient1234!",
        "first_name": "Ahmad",
        "last_name": "Al-Rashid",
        "user_type": UserType.PATIENT,
        "is_active": True,
    },
    {
        "email": "doctor@rmp.local",
        "password": "Doctor1234!",
        "first_name": "Dr. Sara",
        "last_name": "Hassan",
        "user_type": UserType.DOCTOR,
        "is_active": True,
    },
    {
        "email": "pharmacist@rmp.local",
        "password": "Pharmacist1234!",
        "first_name": "Omar",
        "last_name": "Al-Jubouri",
        "user_type": UserType.PHARMACIST,
        "is_active": True,
    },
    {
        "email": "laboratorian@rmp.local",
        "password": "Lab1234!",
        "first_name": "Nour",
        "last_name": "Al-Azawi",
        "user_type": UserType.LABORATORIAN,
        "is_active": True,
    },
]


def _ensure_user_profile(user):
    UserProfile.objects.get_or_create(user=user)


def _ensure_patient_profile(user):
    PatientProfile.objects.get_or_create(user=user)


def _ensure_doctor_profile(user):
    DoctorProfile.objects.get_or_create(
        user=user,
        defaults={
            "specialty": MedicalSpecialty.GENERAL_MEDICINE,
            "verification_status": VerificationStatus.APPROVED,
            "verified_at": timezone.now(),
            "medical_license_number": "DOC-TEST-0001",
        },
    )


def _ensure_pharmacist_profile(user):
    PharmacistProfile.objects.get_or_create(
        user=user,
        defaults={
            "verification_status": VerificationStatus.APPROVED,
            "verified_at": timezone.now(),
            "pharmacist_license_number": "PHARM-TEST-0001",
            "pharmacy_name": "Test Pharmacy",
        },
    )


def _ensure_laboratorian_profile(user):
    LaboratorianProfile.objects.get_or_create(
        user=user,
        defaults={
            "verification_status": VerificationStatus.APPROVED,
            "verified_at": timezone.now(),
            "laboratorian_license_number": "LAB-TEST-0001",
            "laboratory_name": "Test Laboratory",
        },
    )


def _ensure_staff_profile(user):
    """Create StaffProfile with SYSTEM_ADMIN role and all permissions enabled."""
    StaffProfile.objects.get_or_create(
        user=user,
        defaults={
            "staff_role": StaffRole.SYSTEM_ADMIN,
            "department": "Administration",
            "can_approve_professionals": True,
            "can_manage_knowledge_base": True,
            "can_export_datasets": True,
            "can_view_audit_logs": True,
            "has_completed_training": True,
            "training_completed_date": timezone.now(),
        },
    )


PROFILE_BUILDERS = {
    UserType.PATIENT: [_ensure_user_profile, _ensure_patient_profile],
    UserType.DOCTOR: [_ensure_user_profile, _ensure_doctor_profile],
    UserType.PHARMACIST: [_ensure_user_profile, _ensure_pharmacist_profile],
    UserType.LABORATORIAN: [_ensure_user_profile, _ensure_laboratorian_profile],
    UserType.STAFF: [_ensure_staff_profile],
}


class Command(BaseCommand):
    help = "Seed test users (all role types + superuser) for local/Postman testing."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding test users…\n"))

        for spec in USERS:
            email = spec["email"]
            if User.objects.filter(email=email).exists():
                self.stdout.write(f"  SKIP  {email} (already exists)")
                continue

            is_super = spec.get("is_superuser", False)
            user = User.objects.create_user(
                email=email,
                password=spec["password"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                user_type=spec["user_type"],
                is_active=spec.get("is_active", True),
                is_staff=spec.get("is_staff", False),
                is_superuser=is_super,
            )

            # Build role-appropriate profiles
            for builder in PROFILE_BUILDERS.get(spec["user_type"], []):
                builder(user)

            label = "SUPERUSER" if is_super else spec["user_type"].upper()
            self.stdout.write(self.style.SUCCESS(f"  CREATED [{label:15}] {email}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done. Test credentials:"))
        self.stdout.write("")
        self.stdout.write("  Role           | Email                    | Password")
        self.stdout.write("  ---------------+---------------------------+------------------")
        self.stdout.write("  Admin/Superuser| admin@rmp.local          | Admin1234!")
        self.stdout.write("  Patient        | patient@rmp.local        | Patient1234!")
        self.stdout.write("  Doctor         | doctor@rmp.local         | Doctor1234!")
        self.stdout.write("  Pharmacist     | pharmacist@rmp.local     | Pharmacist1234!")
        self.stdout.write("  Laboratorian   | laboratorian@rmp.local   | Lab1234!")
        self.stdout.write("")
        self.stdout.write("  Django Admin panel: http://localhost:8000/admin/")
        self.stdout.write("")
