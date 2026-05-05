from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.common.choices import UserType, VerificationStatus
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)

User = get_user_model()

PROFILE_ME_URL = "/api/profiles/me/"


def _create_active_user(user_type=UserType.PATIENT, email="user@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    if user_type == UserType.PATIENT:
        PatientProfile.objects.create(user=user)
    elif user_type == UserType.DOCTOR:
        DoctorProfile.objects.create(user=user)
    elif user_type == UserType.PHARMACIST:
        PharmacistProfile.objects.create(user=user)
    elif user_type == UserType.LABORATORIAN:
        LaboratorianProfile.objects.create(user=user)
    return user


def _auth_client(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class UserProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.PATIENT)
        self.profile = self.user.user_profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_complete)

    def test_missing_fields_lists_all_required(self):
        missing = self.profile.missing_fields
        self.assertIn("phone_number", missing)
        self.assertIn("gender", missing)
        self.assertIn("national_id", missing)

    def test_complete_when_all_fields_filled(self):
        self.profile.phone_number = "07712345678"
        self.profile.gender = "male"
        self.profile.date_of_birth = "1990-01-01"
        self.profile.governorate = "baghdad"
        self.profile.district = "Karrada"
        self.profile.address = "Some Street"
        self.profile.national_id = "123456789"
        self.profile.save()
        self.assertTrue(self.profile.is_complete)
        self.assertEqual(self.profile.missing_fields, [])


class PatientProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.PATIENT)
        self.profile = self.user.patient_profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_complete)

    def test_complete_when_emergency_contact_filled(self):
        self.profile.emergency_contact_name = "Jane Doe"
        self.profile.emergency_contact_phone = "07712345678"
        self.profile.save()
        self.assertTrue(self.profile.is_complete)


class DoctorProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.DOCTOR, email="doc@example.com")
        self.profile = self.user.doctor_profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_complete)

    def test_missing_fields_includes_license_and_specialty(self):
        missing = self.profile.missing_fields
        self.assertIn("medical_license_number", missing)
        self.assertIn("specialty", missing)


class PharmacistProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.PHARMACIST, email="pharm@example.com")
        self.profile = self.user.pharmacist_profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_complete)

    def test_missing_fields_present(self):
        missing = self.profile.missing_fields
        self.assertIn("pharmacist_license_number", missing)
        self.assertIn("pharmacy_name", missing)


class LaboratorianProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.LABORATORIAN, email="lab@example.com")
        self.profile = self.user.laboratorian_profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_complete)

    def test_missing_fields_present(self):
        missing = self.profile.missing_fields
        self.assertIn("laboratorian_license_number", missing)
        self.assertIn("laboratory_name", missing)


class FullProfileShapeTests(TestCase):
    """GET /api/profiles/me/ returns the new shape with completion and verification."""

    def test_patient_profile_shape(self):
        user = _create_active_user(UserType.PATIENT)
        client = _auth_client(user)
        resp = client.get(PROFILE_ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIn("user", data)
        self.assertIn("user_profile", data)
        self.assertIn("role_profile", data)
        self.assertIn("completion", data)
        self.assertIn("verification", data)

        completion = data["completion"]
        self.assertIn("shared_profile_complete", completion)
        self.assertIn("overall_complete", completion)
        self.assertIn("missing_shared_fields", completion)

        verification = data["verification"]
        self.assertFalse(verification["required"])
        self.assertIsNone(verification["status"])
        self.assertIsNone(verification["is_approved"])

    def test_doctor_verification_block_present(self):
        user = _create_active_user(UserType.DOCTOR, email="doc2@example.com")
        client = _auth_client(user)
        resp = client.get(PROFILE_ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        verification = resp.data["data"]["verification"]
        self.assertTrue(verification["required"])
        self.assertEqual(verification["status"], VerificationStatus.PENDING)
        self.assertFalse(verification["is_approved"])

    def test_overall_complete_false_when_profile_empty(self):
        user = _create_active_user(UserType.PATIENT, email="empty@example.com")
        client = _auth_client(user)
        resp = client.get(PROFILE_ME_URL)
        self.assertFalse(resp.data["data"]["completion"]["overall_complete"])


class VerificationStatusNotWritableTests(TestCase):
    """Doctors/Pharmacists/Laboratorians cannot change verification_status via API."""

    def test_doctor_cannot_set_verification_status(self):
        user = _create_active_user(UserType.DOCTOR, email="doc3@example.com")
        client = _auth_client(user)
        resp = client.patch(
            "/api/profiles/me/doctor/",
            {"verification_status": VerificationStatus.APPROVED},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.doctor_profile.refresh_from_db()
        self.assertEqual(user.doctor_profile.verification_status, VerificationStatus.PENDING)

    def test_pharmacist_cannot_set_verification_status(self):
        user = _create_active_user(UserType.PHARMACIST, email="ph2@example.com")
        client = _auth_client(user)
        resp = client.patch(
            "/api/profiles/me/pharmacist/",
            {"verification_status": VerificationStatus.APPROVED},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.pharmacist_profile.refresh_from_db()
        self.assertEqual(user.pharmacist_profile.verification_status, VerificationStatus.PENDING)


class DoctorSpecialtyOtherValidationTests(TestCase):
    def test_doctor_profile_requires_specialty_other_when_other(self):
        user = _create_active_user(UserType.DOCTOR, email="doc4@example.com")
        client = _auth_client(user)
        resp = client.patch(
            "/api/profiles/me/doctor/",
            {"specialty": "other", "specialty_other": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)
        self.assertIn("details", resp.data["error"])
        self.assertIn("specialty_other", resp.data["error"]["details"])
