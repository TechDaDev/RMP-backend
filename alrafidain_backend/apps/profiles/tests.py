from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.common.choices import StaffRole, UserType, VerificationStatus
from apps.notifications.models import Notification
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    StaffProfile,
    UserProfile,
)

User = get_user_model()

PROFILE_ME_URL = "/api/profiles/me/"


def _create_active_user(user_type=UserType.PATIENT, email="user@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",  # noqa: S106
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
    elif user_type == UserType.STAFF:
        StaffProfile.objects.create(
            user=user,
            staff_role=StaffRole.SYSTEM_ADMIN,
            department="Administration",
            can_approve_professionals=True,
            can_manage_knowledge_base=True,
            can_export_datasets=True,
            can_view_audit_logs=True,
            has_completed_training=True,
        )
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


class DoctorConsultationPricingTests(TestCase):
    def setUp(self):
        self.user = _create_active_user(UserType.DOCTOR, email="doctor-pricing@example.com")
        self.client = _auth_client(self.user)

    def test_doctor_profile_has_consultation_fee_and_currency(self):
        profile_data = self.client.get("/api/profiles/me/doctor/").data["data"]
        self.assertIn("consultation_fee", profile_data)
        self.assertIn("consultation_currency", profile_data)

    def test_negative_consultation_fee_is_rejected(self):
        response = self.client.patch(
            "/api/profiles/me/doctor/",
            {"consultation_fee": "-1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("consultation_fee", response.data["error"]["details"])


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

    def test_staff_profile_shape(self):
        user = _create_active_user(UserType.STAFF, email="staff@example.com")
        client = _auth_client(user)
        resp = client.get(PROFILE_ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIsNotNone(data["role_profile"])
        self.assertEqual(data["role_profile"]["staff_role"], StaffRole.SYSTEM_ADMIN)
        self.assertEqual(data["role_profile"]["role_display"], "System Administrator")
        self.assertIn("allowed_admin_sections", data["role_profile"])
        self.assertIn("verification", data["role_profile"]["allowed_admin_sections"])
        self.assertIn("finance_dashboard", data["role_profile"]["allowed_admin_sections"])
        self.assertFalse(data["verification"]["required"])

    def test_financial_profile_sections_are_finance_only(self):
        user = User.objects.create_user(
            email="financial-sections@example.com",
            password="StrongPass1!",  # noqa: S106
            first_name="Faris",
            last_name="Finance",
            user_type=UserType.STAFF,
            is_active=True,
            is_staff=True,
        )
        UserProfile.objects.create(user=user)
        StaffProfile.objects.create(
            user=user,
            staff_role=StaffRole.FINANCIAL,
            department="Finance",
            is_active=True,
        )

        client = _auth_client(user)
        resp = client.get(PROFILE_ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        sections = set(resp.data["data"]["role_profile"]["allowed_admin_sections"])
        self.assertIn("finance_dashboard", sections)
        self.assertIn("wallet_transactions", sections)
        self.assertNotIn("knowledge_base_documents", sections)
        self.assertNotIn("rag_feedback", sections)
        self.assertNotIn("verification", sections)


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


class AdminVerificationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email="staff-verifications@example.com",
            password="StrongPass1!",  # noqa: S106
            first_name="Staff",
            last_name="Reviewer",
            user_type=UserType.STAFF,
            is_active=True,
            is_staff=True,
        )
        UserProfile.objects.create(user=self.staff)
        StaffProfile.objects.create(
            user=self.staff,
            staff_role=StaffRole.VERIFICATION_OFFICER,
            can_approve_professionals=True,
            is_active=True,
        )
        DoctorProfile.objects.create(
            user=self.staff,
            specialty="general_medicine",
            verification_status=VerificationStatus.APPROVED,
        )
        self.staff_client = _auth_client(self.staff)

        self.patient = _create_active_user(UserType.PATIENT, email="patient-ver@example.com")
        self.doctor = _create_active_user(UserType.DOCTOR, email="doctor-ver@example.com")
        self.pharmacist = _create_active_user(UserType.PHARMACIST, email="pharm-ver@example.com")
        self.laboratorian = _create_active_user(
            UserType.LABORATORIAN,
            email="lab-ver@example.com",
        )

        self.doctor.doctor_profile.medical_license_number = "DOC-100"
        self.doctor.doctor_profile.specialty = "general_medicine"
        self.doctor.doctor_profile.work_address = "Baghdad Clinic"
        self.doctor.doctor_profile.save(
            update_fields=["medical_license_number", "specialty", "work_address", "updated_at"]
        )

        self.pharmacist.pharmacist_profile.pharmacist_license_number = "PH-200"
        self.pharmacist.pharmacist_profile.pharmacy_name = "Rafidain Pharmacy"
        self.pharmacist.pharmacist_profile.pharmacy_address = "Basra Street"
        self.pharmacist.pharmacist_profile.save(
            update_fields=[
                "pharmacist_license_number",
                "pharmacy_name",
                "pharmacy_address",
                "updated_at",
            ]
        )

        self.laboratorian.laboratorian_profile.laboratorian_license_number = "LAB-300"
        self.laboratorian.laboratorian_profile.laboratory_name = "Rafidain Lab"
        self.laboratorian.laboratorian_profile.laboratory_address = "Nineveh Road"
        self.laboratorian.laboratorian_profile.save(
            update_fields=[
                "laboratorian_license_number",
                "laboratory_name",
                "laboratory_address",
                "updated_at",
            ]
        )

    def _list_url(self):
        return "/api/admin/verifications/"

    def _detail_url(self, role, profile_id):
        return f"/api/admin/verifications/{role}/{profile_id}/"

    def _action_url(self, role, profile_id, action):
        return f"/api/admin/verifications/{role}/{profile_id}/{action}/"

    def test_anonymous_cannot_list(self):
        response = self.client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_cannot_list(self):
        response = _auth_client(self.patient).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_cannot_list(self):
        response = _auth_client(self.doctor).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pharmacist_cannot_list(self):
        response = _auth_client(self.pharmacist).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_laboratorian_cannot_list(self):
        response = _auth_client(self.laboratorian).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_list_pending_verifications(self):
        response = self.staff_client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["count"], 3)

    def test_list_includes_only_professional_roles(self):
        response = self.staff_client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = {item["role"] for item in response.data["data"]["results"]}
        self.assertSetEqual(roles, {"doctor", "pharmacist", "laboratorian"})

    def test_role_filter_works(self):
        response = self.staff_client.get(self._list_url() + "?role=doctor")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["role"], "doctor")

    def test_status_filter_works(self):
        self.doctor.doctor_profile.verification_status = VerificationStatus.APPROVED
        self.doctor.doctor_profile.save(update_fields=["verification_status", "updated_at"])

        response = self.staff_client.get(self._list_url() + "?status=approved")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["data"]["count"], 1)
        results = response.data["data"]["results"]
        self.assertTrue(any(item["id"] == self.doctor.doctor_profile.id for item in results))
        self.assertTrue(all(item["status"] == "approved" for item in results))

    def test_search_works_by_email_and_license(self):
        response_email = self.staff_client.get(self._list_url() + "?search=doctor-ver")
        self.assertEqual(response_email.status_code, status.HTTP_200_OK)
        self.assertEqual(response_email.data["data"]["count"], 1)
        self.assertEqual(response_email.data["data"]["results"][0]["role"], "doctor")

        response_license = self.staff_client.get(self._list_url() + "?search=PH-200")
        self.assertEqual(response_license.status_code, status.HTTP_200_OK)
        self.assertEqual(response_license.data["data"]["count"], 1)
        self.assertEqual(response_license.data["data"]["results"][0]["role"], "pharmacist")

    def test_admin_can_retrieve_detail(self):
        response = self.staff_client.get(
            self._detail_url("doctor", self.doctor.doctor_profile.id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["role"], "doctor")
        self.assertEqual(response.data["data"]["status"], VerificationStatus.PENDING)

    def test_admin_can_approve_doctor(self):
        response = self.staff_client.post(
            self._action_url("doctor", self.doctor.doctor_profile.id, "approve"),
            {"note": "Approved after license check"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor.doctor_profile.refresh_from_db()
        self.assertEqual(
            self.doctor.doctor_profile.verification_status, VerificationStatus.APPROVED
        )
        self.assertEqual(self.doctor.doctor_profile.verified_by_id, self.staff.id)
        self.assertIsNotNone(self.doctor.doctor_profile.verified_at)

    def test_admin_can_reject_pharmacist_with_reason(self):
        response = self.staff_client.post(
            self._action_url("pharmacist", self.pharmacist.pharmacist_profile.id, "reject"),
            {"reason": "License document is invalid."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pharmacist.pharmacist_profile.refresh_from_db()
        self.assertEqual(
            self.pharmacist.pharmacist_profile.verification_status,
            VerificationStatus.REJECTED,
        )
        self.assertEqual(
            self.pharmacist.pharmacist_profile.verification_notes,
            "License document is invalid.",
        )

    def test_admin_can_suspend_laboratorian_with_reason(self):
        response = self.staff_client.post(
            self._action_url("laboratorian", self.laboratorian.laboratorian_profile.id, "suspend"),
            {"reason": "Temporary compliance suspension."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.laboratorian.laboratorian_profile.refresh_from_db()
        self.assertEqual(
            self.laboratorian.laboratorian_profile.verification_status,
            VerificationStatus.SUSPENDED,
        )

    def test_reject_without_reason_returns_400(self):
        response = self.staff_client.post(
            self._action_url("pharmacist", self.pharmacist.pharmacist_profile.id, "reject"),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_suspend_without_reason_returns_400(self):
        response = self.staff_client.post(
            self._action_url("laboratorian", self.laboratorian.laboratorian_profile.id, "suspend"),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_approve_own_profile(self):
        response = self.staff_client.post(
            self._action_url("doctor", self.staff.doctor_profile.id, "approve"),
            {"note": "Self approval"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_response_does_not_expose_sensitive_fields(self):
        response = self.staff_client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = response.data["data"]["results"][0]
        self.assertNotIn("password", result["user"])
        self.assertNotIn("token", result["user"])
        self.assertNotIn("medical_license_image", result["profile"])

    def test_action_creates_audit_log_and_notification(self):
        response = self.staff_client.post(
            self._action_url("doctor", self.doctor.doctor_profile.id, "approve"),
            {"note": "Approved."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            AuditLog.objects.filter(
                action="verification_approved",
                target_type="DoctorProfile",
                target_id=str(self.doctor.doctor_profile.id),
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor,
                notification_type="profile",
            ).exists()
        )
