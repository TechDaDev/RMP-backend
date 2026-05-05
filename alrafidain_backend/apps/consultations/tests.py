from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    DoctorRecommendationType,
    MedicalSpecialty,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import (
    Consultation,
    ConsultationResponse,
    ConsultationSymptom,
    Symptom,
    SymptomCategory,
    SymptomSpecialtyRule,
)
from apps.consultations.services import recommend_specialty_from_symptoms
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile

User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_user(email, user_type, active=True):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=active,
    )
    UserProfile.objects.create(user=user)
    if user_type == UserType.PATIENT:
        PatientProfile.objects.create(user=user)
    elif user_type == UserType.DOCTOR:
        DoctorProfile.objects.create(
            user=user,
            specialty=MedicalSpecialty.CARDIOLOGY,
            verification_status=VerificationStatus.APPROVED,
        )
    return user


class TaxonomyTests(TestCase):
    def setUp(self):
        self.user = create_user("p1@example.com", UserType.PATIENT)
        self.client = auth_client(self.user)

        self.c1 = SymptomCategory.objects.create(name="Cardio", display_order=1, is_active=True)
        self.c2 = SymptomCategory.objects.create(
            name="InactiveCat", display_order=2, is_active=False
        )
        Symptom.objects.create(
            category=self.c1, name="Chest Pain", is_red_flag=True, is_active=True
        )
        Symptom.objects.create(category=self.c1, name="Cough", is_red_flag=False, is_active=True)
        Symptom.objects.create(category=self.c2, name="Hidden", is_active=False)

    def test_categories_list_active_only(self):
        resp = self.client.get("/api/consultations/symptom-categories/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [x["name"] for x in resp.data["data"]]
        self.assertIn("Cardio", names)
        self.assertNotIn("InactiveCat", names)

    def test_symptoms_list_active_only(self):
        resp = self.client.get("/api/consultations/symptoms/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [x["name"] for x in resp.data["data"]]
        self.assertIn("Chest Pain", names)
        self.assertIn("Cough", names)
        self.assertNotIn("Hidden", names)

    def test_symptoms_filter_by_category(self):
        resp = self.client.get(f"/api/consultations/symptoms/?category={self.c1.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(x["category"]["id"] == str(self.c1.id) for x in resp.data["data"]))


class RecommendationServiceTests(TestCase):
    def setUp(self):
        self.cat = SymptomCategory.objects.create(name="General", is_active=True)
        self.s1 = Symptom.objects.create(category=self.cat, name="S1", is_active=True)
        self.s2 = Symptom.objects.create(
            category=self.cat, name="S2", is_active=True, is_red_flag=True
        )
        self.s3 = Symptom.objects.create(category=self.cat, name="S3", is_active=False)

        SymptomSpecialtyRule.objects.create(
            symptom=self.s1, specialty=MedicalSpecialty.CARDIOLOGY, weight=3, is_active=True
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.s1, specialty=MedicalSpecialty.INTERNAL_MEDICINE, weight=1, is_active=True
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.s2, specialty=MedicalSpecialty.CARDIOLOGY, weight=2, is_active=True
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.s2, specialty=MedicalSpecialty.DERMATOLOGY, weight=8, is_active=False
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.s3, specialty=MedicalSpecialty.DERMATOLOGY, weight=10, is_active=True
        )

    def test_returns_highest_weighted_specialty(self):
        rec = recommend_specialty_from_symptoms([self.s1.id, self.s2.id])
        self.assertEqual(rec["recommended_specialty"], MedicalSpecialty.CARDIOLOGY)

    def test_red_flag_sets_has_red_flag(self):
        rec = recommend_specialty_from_symptoms([self.s2.id])
        self.assertTrue(rec["has_red_flag"])

    def test_inactive_symptom_ignored(self):
        rec = recommend_specialty_from_symptoms([self.s3.id])
        self.assertEqual(rec["recommended_specialty"], MedicalSpecialty.GENERAL_MEDICINE)

    def test_inactive_rule_ignored(self):
        rec = recommend_specialty_from_symptoms([self.s2.id])
        self.assertNotIn(MedicalSpecialty.DERMATOLOGY, rec["scores"])

    def test_no_rules_returns_general_medicine(self):
        s4 = Symptom.objects.create(category=self.cat, name="NoRule", is_active=True)
        rec = recommend_specialty_from_symptoms([s4.id])
        self.assertEqual(rec["recommended_specialty"], MedicalSpecialty.GENERAL_MEDICINE)


class ConsultationFlowTests(TestCase):
    def setUp(self):
        self.patient = create_user("patient@example.com", UserType.PATIENT)
        self.patient2 = create_user("patient2@example.com", UserType.PATIENT)
        self.pharmacist = create_user("ph@example.com", UserType.PHARMACIST)
        self.laboratorian = create_user("lab@example.com", UserType.LABORATORIAN)
        self.doctor = create_user("doc@example.com", UserType.DOCTOR)
        self.other_doctor = create_user("doc-other@example.com", UserType.DOCTOR)
        self.other_doctor.doctor_profile.specialty = MedicalSpecialty.OTHER
        self.other_doctor.doctor_profile.specialty_other = "Integrative"
        self.other_doctor.doctor_profile.save()

        self.unapproved_doctor = create_user("doc-pending@example.com", UserType.DOCTOR)
        self.unapproved_doctor.doctor_profile.verification_status = VerificationStatus.PENDING
        self.unapproved_doctor.doctor_profile.save()

        self.cat = SymptomCategory.objects.create(name="Emergency", is_active=True)
        self.symptom = Symptom.objects.create(
            category=self.cat, name="Chest pain", is_red_flag=True, is_active=True
        )
        self.symptom2 = Symptom.objects.create(
            category=self.cat, name="Palpitations", is_active=True
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.symptom, specialty=MedicalSpecialty.CARDIOLOGY, weight=5
        )
        SymptomSpecialtyRule.objects.create(
            symptom=self.symptom2, specialty=MedicalSpecialty.CARDIOLOGY, weight=1
        )

        self.patient_client = auth_client(self.patient)
        self.patient2_client = auth_client(self.patient2)
        self.doctor_client = auth_client(self.doctor)
        self.other_doctor_client = auth_client(self.other_doctor)
        self.unapproved_doctor_client = auth_client(self.unapproved_doctor)
        self.pharmacist_client = auth_client(self.pharmacist)
        self.laboratorian_client = auth_client(self.laboratorian)

    def create_consultation(self, client=None, selected_specialty=None):
        payload = {
            "symptom_ids": [str(self.symptom.id), str(self.symptom2.id)],
            "duration": ConsultationDuration.ONE_TO_THREE_DAYS,
            "severity": SeverityLevel.MODERATE,
            "has_fever": False,
            "has_pain": True,
            "has_breathing_difficulty": False,
            "previous_visit_for_same_issue": False,
        }
        if selected_specialty is not None:
            payload["selected_specialty"] = selected_specialty
        return (client or self.patient_client).post("/api/consultations/", payload, format="json")

    def test_patient_can_create_consultation(self):
        resp = self.create_consultation()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        self.assertEqual(Consultation.objects.count(), 1)
        c = Consultation.objects.first()
        self.assertEqual(c.patient_id, self.patient.id)

    def test_non_patient_cannot_create_consultation(self):
        resp = self.create_consultation(client=self.pharmacist_client)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consultation_creates_symptom_rows(self):
        self.create_consultation()
        c = Consultation.objects.first()
        self.assertEqual(ConsultationSymptom.objects.filter(consultation=c).count(), 2)

    def test_recommended_and_selected_specialty_behavior(self):
        self.create_consultation()
        c = Consultation.objects.first()
        self.assertEqual(c.recommended_specialty, MedicalSpecialty.CARDIOLOGY)
        self.assertEqual(c.selected_specialty, MedicalSpecialty.CARDIOLOGY)

    def test_red_flag_sets_emergency_warning(self):
        self.create_consultation()
        c = Consultation.objects.first()
        self.assertTrue(c.has_emergency_warning)

    def test_patient_cannot_set_forbidden_fields(self):
        payload = {
            "symptom_ids": [str(self.symptom.id)],
            "duration": ConsultationDuration.ONE_TO_THREE_DAYS,
            "severity": SeverityLevel.MODERATE,
            "assigned_doctor": str(self.doctor.id),
            "status": ConsultationStatus.CLOSED,
            "ai_predicted_disease": "X",
        }
        resp = self.patient_client.post("/api/consultations/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        c = Consultation.objects.first()
        self.assertIsNone(c.assigned_doctor)
        self.assertEqual(c.status, ConsultationStatus.SUBMITTED)
        self.assertEqual(c.ai_predicted_disease, "")

    def test_audit_log_created_for_consultation_created(self):
        self.create_consultation()
        self.assertTrue(AuditLog.objects.filter(action="consultation_created").exists())

    def test_patient_detail_hides_ai_disease_fields(self):
        self.create_consultation()
        c = Consultation.objects.first()
        c.ai_predicted_disease = "Hidden Disease"
        c.ai_predicted_disease_confidence = 88.5
        c.ai_prediction_notes = "Doctor only"
        c.save()

        resp = self.patient_client.get(f"/api/consultations/{c.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertNotIn("ai_predicted_disease", data)
        self.assertNotIn("ai_predicted_disease_confidence", data)
        self.assertNotIn("ai_prediction_notes", data)

    def test_approved_doctor_can_list_pending_matching_specialty(self):
        self.create_consultation()
        resp = self.doctor_client.get("/api/consultations/doctor/pending/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

    def test_unapproved_doctor_cannot_list_pending(self):
        self.create_consultation()
        resp = self.unapproved_doctor_client.get("/api/consultations/doctor/pending/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_cannot_list_unrelated_specialty(self):
        self.create_consultation(selected_specialty=MedicalSpecialty.CARDIOLOGY)
        self.other_doctor.doctor_profile.specialty = MedicalSpecialty.DERMATOLOGY
        self.other_doctor.doctor_profile.specialty_other = ""
        self.other_doctor.doctor_profile.save()
        resp = self.other_doctor_client.get("/api/consultations/doctor/pending/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 0)

    def test_approved_doctor_can_accept_submitted(self):
        self.create_consultation()
        c = Consultation.objects.first()
        resp = self.doctor_client.post(f"/api/consultations/{c.id}/accept/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        c.refresh_from_db()
        self.assertEqual(c.assigned_doctor_id, self.doctor.id)
        self.assertEqual(c.status, ConsultationStatus.ACCEPTED)
        self.assertIsNotNone(c.accepted_at)

    def test_doctor_cannot_accept_already_accepted(self):
        self.create_consultation()
        c = Consultation.objects.first()
        self.doctor_client.post(f"/api/consultations/{c.id}/accept/", {}, format="json")
        resp = self.other_doctor_client.post(
            f"/api/consultations/{c.id}/accept/", {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assigned_doctor_can_view_doctor_detail_with_ai_fields(self):
        self.create_consultation()
        c = Consultation.objects.first()
        c.assigned_doctor = self.doctor
        c.status = ConsultationStatus.ACCEPTED
        c.ai_predicted_disease = "Doctor Visible"
        c.ai_predicted_disease_confidence = 73.5
        c.ai_prediction_notes = "internal"
        c.save()

        resp = self.doctor_client.get(f"/api/consultations/{c.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("ai_predicted_disease", resp.data["data"])

    def test_unassigned_doctor_cannot_view_detail(self):
        self.create_consultation()
        c = Consultation.objects.first()
        resp = self.other_doctor_client.get(f"/api/consultations/{c.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_assigned_doctor_can_create_response(self):
        self.create_consultation()
        c = Consultation.objects.first()
        c.assigned_doctor = self.doctor
        c.status = ConsultationStatus.ACCEPTED
        c.save()

        resp = self.doctor_client.post(
            f"/api/consultations/{c.id}/responses/",
            {
                "response_text": "Please do ECG.",
                "recommendation_type": DoctorRecommendationType.NEEDS_LAB_TEST,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationStatus.DOCTOR_RESPONDED)
        self.assertTrue(ConsultationResponse.objects.filter(consultation=c).exists())

    def test_assigned_doctor_can_close(self):
        self.create_consultation()
        c = Consultation.objects.first()
        c.assigned_doctor = self.doctor
        c.status = ConsultationStatus.ACCEPTED
        c.save()
        resp = self.doctor_client.post(f"/api/consultations/{c.id}/close/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationStatus.CLOSED)
        self.assertIsNotNone(c.closed_at)

    def test_audit_logs_for_accept_response_close(self):
        self.create_consultation()
        c = Consultation.objects.first()
        self.doctor_client.post(f"/api/consultations/{c.id}/accept/", {}, format="json")
        self.doctor_client.post(
            f"/api/consultations/{c.id}/responses/",
            {
                "response_text": "Take rest",
                "recommendation_type": DoctorRecommendationType.GENERAL_ADVICE,
            },
            format="json",
        )
        self.doctor_client.post(f"/api/consultations/{c.id}/close/", {}, format="json")
        self.assertTrue(AuditLog.objects.filter(action="consultation_accepted").exists())
        self.assertTrue(AuditLog.objects.filter(action="consultation_response_created").exists())
        self.assertTrue(AuditLog.objects.filter(action="consultation_closed").exists())

    def test_doctor_specialty_other_only_handles_other(self):
        self.create_consultation(selected_specialty=MedicalSpecialty.CARDIOLOGY)
        c = Consultation.objects.first()
        resp = self.other_doctor_client.post(
            f"/api/consultations/{c.id}/accept/", {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        c.selected_specialty = MedicalSpecialty.OTHER
        c.selected_specialty_other = "Custom"
        c.save()
        resp2 = self.other_doctor_client.post(
            f"/api/consultations/{c.id}/accept/", {}, format="json"
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_pharmacist_laboratorian_access_restricted(self):
        resp1 = self.create_consultation(client=self.pharmacist_client)
        resp2 = self.create_consultation(client=self.laboratorian_client)
        self.assertEqual(resp1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_cannot_view_other_patient_consultation(self):
        self.create_consultation()
        c = Consultation.objects.first()
        resp = self.patient2_client.get(f"/api/consultations/{c.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
