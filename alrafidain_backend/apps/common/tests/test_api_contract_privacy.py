"""
Phase 13 — API Contract Privacy Regression Tests

Cross-cutting integration tests that verify the API contract's privacy and
role-isolation guarantees. Tests here focus on boundaries NOT already covered
in app-specific test files.

Covers:
- Health endpoint includes version field (contract freeze check)
- Patient cannot access RAG endpoints (API-level check for all three RAG paths)
- Pharmacist cannot read consultation messages
- Pharmacist cannot list lab orders
- Laboratorian cannot list consultation messages
- Knowledge base endpoints require staff (anon denied)
- Unauthenticated access to protected endpoints returns 401
- RAG analytics/export endpoints return 401 for unauthenticated and 403 for non-staff
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    ConsultationStatus,
    MedicalSpecialty,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _make_patient(email="cpt_patient@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Pat", last_name="Ient",
        user_type=UserType.PATIENT, is_active=True,
    )
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def _make_doctor(email="cpt_doctor@example.com", approved=True):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Doc", last_name="Tor",
        user_type=UserType.DOCTOR, is_active=True,
    )
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def _make_pharmacist(email="cpt_pharmacist@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Pha", last_name="Mac",
        user_type=UserType.PHARMACIST, is_active=True,
    )
    UserProfile.objects.create(user=user)
    PharmacistProfile.objects.create(user=user, verification_status=VerificationStatus.APPROVED)
    return user


def _make_laboratorian(email="cpt_lab@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Lab", last_name="Tech",
        user_type=UserType.LABORATORIAN, is_active=True,
    )
    UserProfile.objects.create(user=user)
    LaboratorianProfile.objects.create(user=user, verification_status=VerificationStatus.APPROVED)
    return user


def _make_staff(email="cpt_staff@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Sta", last_name="Ff",
        user_type=UserType.DOCTOR, is_active=True, is_staff=True,
    )
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED,
    )
    return user


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class HealthEndpointContractTest(TestCase):
    """Verify the health endpoint meets the v0.1.0 contract."""

    def test_health_returns_200(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)

    def test_health_returns_status_ok(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.json()["status"], "ok")

    def test_health_returns_service_name(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.json()["service"], "alrafidain-backend")

    def test_health_returns_version(self):
        resp = self.client.get("/api/health/")
        self.assertIn("version", resp.json())
        self.assertEqual(resp.json()["version"], "0.1.0")

    def test_health_accessible_without_auth(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Unauthenticated 401 checks
# ---------------------------------------------------------------------------

class UnauthenticatedAccessTest(TestCase):
    """Critical endpoints must return 401 for unauthenticated requests."""

    def _assert_401(self, method, path, data=None):
        client = APIClient()
        fn = getattr(client, method)
        kwargs = {"format": "json"}
        if data:
            kwargs["data"] = data
        resp = fn(path, **kwargs)
        self.assertEqual(resp.status_code, 401, f"Expected 401 on {method.upper()} {path}, got {resp.status_code}")

    def test_consultations_list_requires_auth(self):
        self._assert_401("get", "/api/consultations/my/")

    def test_profiles_me_requires_auth(self):
        self._assert_401("get", "/api/profiles/me/")

    def test_prescriptions_list_requires_auth(self):
        self._assert_401("get", "/api/prescriptions/my/")

    def test_lab_orders_list_requires_auth(self):
        self._assert_401("get", "/api/lab-orders/my/")

    def test_notifications_list_requires_auth(self):
        self._assert_401("get", "/api/notifications/")

    def test_knowledge_base_requires_auth(self):
        self._assert_401("get", "/api/knowledge-base/documents/")

    def test_rag_query_requires_auth(self):
        self._assert_401("post", "/api/rag/doctor/query/", data={"query_text": "test"})

    def test_rag_analytics_requires_auth(self):
        self._assert_401("get", "/api/rag/admin/analytics/summary/")

    def test_rag_export_requires_auth(self):
        self._assert_401("post", "/api/rag/admin/exports/dataset/", data={"format": "json"})


# ---------------------------------------------------------------------------
# Patient cannot use RAG (cross-module boundary)
# ---------------------------------------------------------------------------

class PatientCannotAccessRAGTest(TestCase):
    """Patients must never be able to call any RAG endpoint."""

    def setUp(self):
        self.patient = _make_patient("cpt_p_rag@example.com")
        self.client_ = _auth_client(self.patient)

    def test_patient_cannot_call_general_rag_query(self):
        resp = self.client_.post(
            "/api/rag/doctor/query/",
            {"query_text": "What is hypertension?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_patient_cannot_call_rag_analytics(self):
        resp = self.client_.get("/api/rag/admin/analytics/summary/")
        self.assertEqual(resp.status_code, 403)

    def test_patient_cannot_export_rag_dataset(self):
        resp = self.client_.post(
            "/api/rag/admin/exports/dataset/",
            {"format": "json"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Pharmacist cross-module isolation
# ---------------------------------------------------------------------------

class PharmacistCrossModuleIsolationTest(TestCase):
    """Pharmacists must not access consultations, messages, or lab orders."""

    def setUp(self):
        self.patient = _make_patient("cpt_ph_p@example.com")
        self.doctor = _make_doctor("cpt_ph_d@example.com")
        self.pharmacist = _make_pharmacist("cpt_ph_ph@example.com")
        self.pharm_client = _auth_client(self.pharmacist)
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
            duration="less_than_24_hours",
            severity="mild",
        )

    def test_pharmacist_cannot_list_consultation_messages(self):
        resp = self.pharm_client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )
        self.assertIn(resp.status_code, [403, 404])

    def test_pharmacist_cannot_list_lab_orders(self):
        resp = self.pharm_client.get("/api/lab-orders/my/")
        # Pharmacists are not patients; should be denied
        self.assertIn(resp.status_code, [403, 404])

    def test_pharmacist_cannot_view_consultation_detail(self):
        resp = self.pharm_client.get(f"/api/consultations/{self.consultation.pk}/")
        self.assertIn(resp.status_code, [403, 404])


# ---------------------------------------------------------------------------
# Laboratorian cross-module isolation
# ---------------------------------------------------------------------------

class LaboratorianCrossModuleIsolationTest(TestCase):
    """Laboratorians must not access prescriptions, messages, or RAG."""

    def setUp(self):
        self.patient = _make_patient("cpt_lb_p@example.com")
        self.doctor = _make_doctor("cpt_lb_d@example.com")
        self.laboratorian = _make_laboratorian("cpt_lb_l@example.com")
        self.lab_client = _auth_client(self.laboratorian)
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
            duration="less_than_24_hours",
            severity="mild",
        )

    def test_laboratorian_cannot_list_prescriptions(self):
        resp = self.lab_client.get("/api/prescriptions/my/")
        self.assertIn(resp.status_code, [403, 404])

    def test_laboratorian_cannot_list_consultation_messages(self):
        resp = self.lab_client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )
        self.assertIn(resp.status_code, [403, 404])

    def test_laboratorian_cannot_call_rag(self):
        resp = self.lab_client.post(
            "/api/rag/doctor/query/",
            {"query_text": "test"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# RAG admin endpoints deny non-staff
# ---------------------------------------------------------------------------

class RAGAdminEndpointsRequireStaffTest(TestCase):
    """RAG analytics and export are staff-only."""

    def setUp(self):
        self.doctor = _make_doctor("cpt_ras_d@example.com")
        self.doctor_client = _auth_client(self.doctor)
        self.staff = _make_staff("cpt_ras_s@example.com")
        self.staff_client = _auth_client(self.staff)

    def test_doctor_cannot_view_rag_analytics(self):
        resp = self.doctor_client.get("/api/rag/admin/analytics/summary/")
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_view_rag_analytics(self):
        resp = self.staff_client.get("/api/rag/admin/analytics/summary/")
        self.assertEqual(resp.status_code, 200)

    def test_doctor_cannot_export_rag_dataset(self):
        resp = self.doctor_client.post(
            "/api/rag/admin/exports/dataset/",
            {"format": "json"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_export_rag_dataset(self):
        resp = self.staff_client.post(
            "/api/rag/admin/exports/dataset/",
            {"format": "json"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
