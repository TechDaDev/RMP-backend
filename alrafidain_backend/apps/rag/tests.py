"""
Tests for the RAG app (Phase 12C).

All DeepSeek LLM calls are mocked.
All pgvector semantic search calls are mocked (CosineDistance not supported in SQLite test DB).
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
    KnowledgeApprovalStatus,
    KnowledgeAudience,
    KnowledgeDocumentType,
    KnowledgeLanguage,
    LabTestCategory,
    MedicalSpecialty,
    RAGResponseStatus,
    RAGSafetyLevel,
    RAGServiceContext,
    UserType,
    VerificationStatus,
)
from apps.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile

from .models import RAGQuery, RAGResponse, RAGRetrievedChunk
from .permissions import (
    can_access_consultation_rag,
    can_access_lab_result_rag,
    is_approved_doctor,
)
from .services import (
    build_consultation_summary_for_rag,
    build_lab_result_summary_for_rag,
    doctor_can_use_rag,
    run_doctor_rag_query,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Mock LLM response
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = {
    "content": "Mock doctor-facing RAG answer.\n\nSources:\n- Source 1",
    "model": "deepseek-chat",
    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    "raw": {"mock": True},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_patient(email="patient@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Pat",
        last_name="Ient",
        user_type=UserType.PATIENT,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def create_doctor(email="doctor@example.com", approved=True):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Doc",
        last_name="Tor",
        user_type=UserType.DOCTOR,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def _mock_chunk():
    """Build a minimal mock knowledge chunk dict as returned by semantic_search_approved_chunks."""
    doc = MagicMock()
    doc.id = "00000000-0000-0000-0000-000000000001"
    doc.title = "Test Medical Document"
    doc.document_type = "clinical_guideline"
    chunk = MagicMock()
    chunk.pk = "00000000-0000-0000-0000-000000000002"
    chunk.id = chunk.pk
    chunk.document = doc
    chunk.page_number = 1
    chunk.section_title = "Introduction"
    chunk.text = "Test chunk text about hypertension management."
    return {"chunk": chunk, "score": 0.87, "distance": 0.13, "rank": 1}


def _create_real_chunk(uploader):
    """Create a real KnowledgeChunk in the test DB."""
    doc = KnowledgeDocument.objects.create(
        title="Test Medical Document",
        document_type=KnowledgeDocumentType.CLINICAL_GUIDELINE,
        language=KnowledgeLanguage.ENGLISH,
        audience=KnowledgeAudience.DOCTOR,
        approval_status=KnowledgeApprovalStatus.APPROVED,
        uploaded_by=uploader,
        is_active=True,
    )
    chunk = KnowledgeChunk.objects.create(
        document=doc,
        chunk_index=0,
        text="Test chunk text about hypertension management.",
        page_number=1,
        section_title="Introduction",
        is_active=True,
    )
    return {"chunk": chunk, "score": 0.87, "distance": 0.13, "rank": 1}


# ---------------------------------------------------------------------------
# Unit tests – permissions
# ---------------------------------------------------------------------------


class IsApprovedDoctorTest(TestCase):
    def test_approved_doctor_returns_true(self):
        doctor = create_doctor(email="approveddoc@example.com")
        self.assertTrue(is_approved_doctor(doctor))

    def test_pending_doctor_returns_false(self):
        doctor = create_doctor(email="pendingdoc@example.com", approved=False)
        self.assertFalse(is_approved_doctor(doctor))

    def test_patient_returns_false(self):
        patient = create_patient(email="pat2@example.com")
        self.assertFalse(is_approved_doctor(patient))

    def test_anonymous_user_returns_false(self):
        anon = MagicMock()
        anon.is_authenticated = False
        self.assertFalse(is_approved_doctor(anon))

    def test_none_returns_false(self):
        self.assertFalse(is_approved_doctor(None))


class CanAccessConsultationRagTest(TestCase):
    def setUp(self):
        self.doctor = create_doctor(email="doctor_c@example.com")
        self.other_doctor = create_doctor(email="other_doctor_c@example.com")
        self.consultation = MagicMock()
        self.consultation.assigned_doctor_id = self.doctor.pk

    def test_assigned_doctor_can_access(self):
        self.assertTrue(can_access_consultation_rag(self.doctor, self.consultation))

    def test_other_doctor_cannot_access(self):
        self.assertFalse(can_access_consultation_rag(self.other_doctor, self.consultation))

    def test_patient_cannot_access(self):
        patient = create_patient(email="pat_c@example.com")
        self.assertFalse(can_access_consultation_rag(patient, self.consultation))


class CanAccessLabResultRagTest(TestCase):
    def setUp(self):
        self.doctor = create_doctor(email="doctor_lr@example.com")
        self.other_doctor = create_doctor(email="other_lr@example.com")
        self.lab_result = MagicMock()
        self.lab_result.doctor_id = self.doctor.pk

    def test_ordering_doctor_can_access(self):
        self.assertTrue(can_access_lab_result_rag(self.doctor, self.lab_result))

    def test_other_doctor_cannot_access(self):
        self.assertFalse(can_access_lab_result_rag(self.other_doctor, self.lab_result))


# ---------------------------------------------------------------------------
# Unit tests – services
# ---------------------------------------------------------------------------


class DoctorCanUseRagTest(TestCase):
    def test_approved_doctor_can_use(self):
        doctor = create_doctor(email="canuserag@example.com")
        self.assertTrue(doctor_can_use_rag(doctor))

    def test_pending_doctor_cannot_use(self):
        doctor = create_doctor(email="canuserag_pending@example.com", approved=False)
        self.assertFalse(doctor_can_use_rag(doctor))


@patch("apps.knowledge_base.services.semantic_search_approved_chunks")
class RunDoctorRagQueryNoContextTest(TestCase):
    """When semantic search returns no chunks, no LLM call is made and status is no_context."""

    def setUp(self):
        self.doctor = create_doctor(email="nocontext@example.com")

    def test_no_context_creates_rag_response(self, mock_search):
        mock_search.return_value = []

        rag_query, rag_response = run_doctor_rag_query(
            doctor=self.doctor,
            query_text="What is hypertension?",
            service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
        )

        self.assertEqual(rag_response.status, RAGResponseStatus.NO_CONTEXT)
        self.assertEqual(rag_response.patient_visible, False)
        self.assertEqual(rag_response.doctor_review_required, True)
        self.assertEqual(RAGQuery.objects.count(), 1)
        self.assertEqual(RAGRetrievedChunk.objects.count(), 0)
        mock_search.assert_called_once()


class RunDoctorRagQuerySuccessTest(TestCase):
    """When semantic search returns chunks and LLM succeeds, status is success."""

    def setUp(self):
        self.doctor = create_doctor(email="success@example.com")
        self.real_hit = _create_real_chunk(self.doctor)

    def test_success_creates_rag_response(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = MOCK_LLM_RESPONSE

        with patch("apps.knowledge_base.services.semantic_search_approved_chunks", return_value=[self.real_hit]):
            rag_query, rag_response = run_doctor_rag_query(
                doctor=self.doctor,
                query_text="Explain hypertension management.",
                service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
                llm_client=mock_client,
            )

        self.assertEqual(rag_response.status, RAGResponseStatus.SUCCESS)
        self.assertIn("Mock doctor-facing RAG answer", rag_response.response_text)
        self.assertEqual(rag_response.patient_visible, False)
        self.assertEqual(rag_response.doctor_review_required, True)
        self.assertEqual(rag_response.token_input, 100)
        self.assertEqual(rag_response.token_output, 50)
        self.assertEqual(RAGRetrievedChunk.objects.count(), 1)
        mock_client.chat.assert_called_once()

    def test_unapproved_doctor_raises_permission_error(self):
        unapproved = create_doctor(email="unapp@example.com", approved=False)
        with self.assertRaises(PermissionError):
            run_doctor_rag_query(
                doctor=unapproved,
                query_text="What is diabetes?",
                service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
            )

    def test_llm_failure_creates_failed_response(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("API unreachable")

        with patch("apps.knowledge_base.services.semantic_search_approved_chunks", return_value=[self.real_hit]):
            rag_query, rag_response = run_doctor_rag_query(
                doctor=self.doctor,
                query_text="Explain diabetes.",
                service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
                llm_client=mock_client,
            )

        self.assertEqual(rag_response.status, RAGResponseStatus.FAILED)
        self.assertIn("API unreachable", rag_response.error_message)
        self.assertEqual(rag_response.patient_visible, False)


# ---------------------------------------------------------------------------
# Unit tests – summary builders
# ---------------------------------------------------------------------------


class BuildConsultationSummaryTest(TestCase):
    def test_builds_summary_with_all_fields(self):
        consultation = MagicMock()
        consultation.pk = "00000000-0000-0000-0000-000000000099"
        consultation.status = "submitted"
        consultation.selected_specialty = "cardiology"
        consultation.additional_notes = "Patient reports chest pain."
        consultation.current_medications_related = "Aspirin 100mg"
        consultation.has_fever = True
        consultation.has_pain = True
        consultation.has_breathing_difficulty = False
        consultation.has_emergency_warning = False
        consultation.severity = "moderate"
        consultation.duration = "3 days"

        summary = build_consultation_summary_for_rag(consultation)

        self.assertIn("cardiology", summary)
        self.assertIn("chest pain", summary)
        self.assertIn("Aspirin 100mg", summary)
        self.assertIn("fever", summary)
        self.assertIn("moderate", summary)

    def test_builds_summary_minimal(self):
        consultation = MagicMock()
        consultation.pk = "00000000-0000-0000-0000-000000000100"
        consultation.status = "submitted"
        consultation.selected_specialty = None
        consultation.additional_notes = None
        consultation.current_medications_related = None
        consultation.has_fever = False
        consultation.has_pain = False
        consultation.has_breathing_difficulty = False
        consultation.has_emergency_warning = False
        consultation.severity = None
        consultation.duration = None

        summary = build_consultation_summary_for_rag(consultation)
        self.assertIn("Consultation ID", summary)


class BuildLabResultSummaryTest(TestCase):
    def test_builds_summary_with_all_fields(self):
        lab_result = MagicMock()
        lab_result.pk = "00000000-0000-0000-0000-000000000101"
        lab_result.lab_order_item.test_name = "HbA1c"
        lab_result.status = "released"
        lab_result.value_type = "numeric"
        lab_result.numeric_value = 7.5
        lab_result.unit = "%"
        lab_result.reference_range = "4.0–5.6%"
        lab_result.flag = "high"
        lab_result.text_value = None
        lab_result.laboratorian_notes = "Repeat in 3 months."
        lab_result.doctor_notes = "Start lifestyle changes."

        summary = build_lab_result_summary_for_rag(lab_result)

        self.assertIn("HbA1c", summary)
        self.assertIn("7.5", summary)
        self.assertIn("high", summary)
        self.assertIn("Repeat in 3 months", summary)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@patch("apps.knowledge_base.services.semantic_search_approved_chunks")
class DoctorGeneralRAGQueryViewTest(TestCase):
    URL = "/api/rag/doctor/query/"

    def setUp(self):
        self.doctor = create_doctor(email="doc_api@example.com")
        self.patient = create_patient(email="pat_api@example.com")
        self.real_hit = _create_real_chunk(self.doctor)

    def test_approved_doctor_with_no_context_returns_200(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        resp = client.post(self.URL, {"question": "What is hypertension?"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], RAGResponseStatus.NO_CONTEXT)
        self.assertFalse(resp.data["patient_visible"])

    def test_approved_doctor_success_returns_200(self, mock_search):
        mock_search.return_value = [self.real_hit]
        mock_client = MagicMock()
        mock_client.chat.return_value = MOCK_LLM_RESPONSE

        with patch("apps.rag.llm_clients.deepseek_client.DeepSeekClient", return_value=mock_client):
            client = auth_client(self.doctor)
            resp = client.post(
                self.URL,
                {"question": "Explain HbA1c.", "top_k": 3},
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], RAGResponseStatus.SUCCESS)
        self.assertIn("sources", resp.data)

    def test_patient_receives_403(self, mock_search):
        client = auth_client(self.patient)
        resp = client.post(self.URL, {"question": "What is diabetes?"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_receives_401(self, mock_search):
        client = APIClient()
        resp = client.post(self.URL, {"question": "Test?"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_missing_question_returns_400(self, mock_search):
        client = auth_client(self.doctor)
        resp = client.post(self.URL, {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_top_k_exceeding_max_returns_400(self, mock_search):
        client = auth_client(self.doctor)
        resp = client.post(self.URL, {"question": "Test?", "top_k": 999}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_pending_doctor_receives_403(self, mock_search):
        pending = create_doctor(email="pending_api@example.com", approved=False)
        client = auth_client(pending)
        resp = client.post(self.URL, {"question": "What is sepsis?"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_response_does_not_expose_prompt_or_raw(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        resp = client.post(self.URL, {"question": "Test?"}, format="json")
        self.assertNotIn("prompt_text", resp.data)
        self.assertNotIn("raw_response", resp.data)

    def test_audit_log_created(self, mock_search):
        mock_search.return_value = []
        before = AuditLog.objects.count()
        client = auth_client(self.doctor)
        client.post(self.URL, {"question": "Test audit?"}, format="json")
        self.assertGreater(AuditLog.objects.count(), before)


@patch("apps.knowledge_base.services.semantic_search_approved_chunks")
class ConsultationRAGSupportViewTest(TestCase):
    def setUp(self):
        from apps.consultations.models import Consultation
        from apps.common.choices import ConsultationStatus

        self.doctor = create_doctor(email="doc_consult@example.com")
        self.other_doctor = create_doctor(email="other_consult@example.com")
        self.patient = create_patient(email="pat_consult@example.com")
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        )

    def url(self):
        return f"/api/rag/consultations/{self.consultation.pk}/support/"

    def test_assigned_doctor_no_context_200(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], RAGResponseStatus.NO_CONTEXT)

    def test_other_doctor_gets_403(self, mock_search):
        client = auth_client(self.other_doctor)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_patient_gets_403(self, mock_search):
        client = auth_client(self.patient)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_consultation_service_context_recorded(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        client.post(self.url(), {}, format="json")
        rag_q = RAGQuery.objects.last()
        self.assertEqual(rag_q.service_context, RAGServiceContext.CONSULTATION)
        self.assertEqual(str(rag_q.object_id), str(self.consultation.pk))


@patch("apps.knowledge_base.services.semantic_search_approved_chunks")
class LabResultRAGSupportViewTest(TestCase):
    def setUp(self):
        from apps.consultations.models import Consultation
        from apps.common.choices import ConsultationStatus
        from apps.lab_orders.models import LabResult, LabOrder, LabOrderItem
        from apps.common.choices import (
            LabOrderItemStatus,
            LabResultStatus,
            LabResultValueType,
        )
        from apps.profiles.models import LaboratorianProfile

        self.doctor = create_doctor(email="doc_lab@example.com")
        self.other_doctor = create_doctor(email="other_lab@example.com")
        self.patient = create_patient(email="pat_lab@example.com")

        # create laboratorian
        lab_user = User.objects.create_user(
            email="labuser@example.com",
            password="StrongPass1!",
            user_type=UserType.LABORATORIAN,
            is_active=True,
        )
        UserProfile.objects.create(user=lab_user)
        LaboratorianProfile.objects.create(
            user=lab_user,
            verification_status=VerificationStatus.APPROVED,
        )

        consultation = Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
            duration="less_than_24_hours",
            severity="mild",
        )
        lab_order = LabOrder.objects.create(
            consultation=consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        lab_item = LabOrderItem.objects.create(
            lab_order=lab_order,
            test_name="HbA1c",
            category=LabTestCategory.BIOCHEMISTRY,
            sample_type="Blood",
            instructions="Standard",
        )
        self.lab_result = LabResult.objects.create(
            lab_order=lab_order,
            lab_order_item=lab_item,
            laboratorian=lab_user,
            doctor=self.doctor,
            patient=self.patient,
            status=LabResultStatus.SUBMITTED,
            value_type=LabResultValueType.NUMERIC,
            numeric_value=7.5,
            unit="%",
        )

    def url(self):
        return f"/api/rag/lab-results/{self.lab_result.pk}/support/"

    def test_ordering_doctor_no_context_200(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], RAGResponseStatus.NO_CONTEXT)

    def test_other_doctor_gets_403(self, mock_search):
        client = auth_client(self.other_doctor)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_lab_result_service_context_recorded(self, mock_search):
        mock_search.return_value = []
        client = auth_client(self.doctor)
        client.post(self.url(), {}, format="json")
        rag_q = RAGQuery.objects.last()
        self.assertEqual(rag_q.service_context, RAGServiceContext.LAB_RESULT)


# ---------------------------------------------------------------------------
# Safety invariant tests
# ---------------------------------------------------------------------------


class RAGResponseSafetyInvariantsTest(TestCase):
    def setUp(self):
        self.doctor = create_doctor(email="safety@example.com")

    @patch("apps.knowledge_base.services.semantic_search_approved_chunks")
    def test_patient_visible_always_false(self, mock_search):
        mock_search.return_value = []
        _, rag_response = run_doctor_rag_query(
            doctor=self.doctor,
            query_text="Test safety invariant.",
            service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
        )
        self.assertFalse(rag_response.patient_visible)

    @patch("apps.knowledge_base.services.semantic_search_approved_chunks")
    def test_doctor_review_required_always_true(self, mock_search):
        mock_search.return_value = []
        _, rag_response = run_doctor_rag_query(
            doctor=self.doctor,
            query_text="Test doctor review.",
            service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
        )
        self.assertTrue(rag_response.doctor_review_required)

    @patch("apps.knowledge_base.services.semantic_search_approved_chunks")
    def test_safety_level_is_doctor_only(self, mock_search):
        mock_search.return_value = []
        _, rag_response = run_doctor_rag_query(
            doctor=self.doctor,
            query_text="Test safety level.",
            service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
        )
        self.assertEqual(rag_response.safety_level, RAGSafetyLevel.DOCTOR_ONLY)
