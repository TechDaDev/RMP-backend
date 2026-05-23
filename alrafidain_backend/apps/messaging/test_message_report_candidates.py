from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    MedicalSpecialty,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.patient_records.models import PatientMedicalReport
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile

User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_user(email, user_type):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",  # noqa: S106 - test fixture credential
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    if user_type == UserType.PATIENT:
        PatientProfile.objects.create(user=user)
    if user_type == UserType.DOCTOR:
        DoctorProfile.objects.create(
            user=user,
            specialty=MedicalSpecialty.INTERNAL_MEDICINE,
            verification_status=VerificationStatus.APPROVED,
        )
    return user


def create_consultation(patient, doctor):
    return Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=ConsultationStatus.ACCEPTED,
        recommended_specialty=MedicalSpecialty.INTERNAL_MEDICINE,
        selected_specialty=MedicalSpecialty.INTERNAL_MEDICINE,
        duration=ConsultationDuration.ONE_TO_THREE_DAYS,
        severity=SeverityLevel.MODERATE,
    )


class MessageReportCandidateHookTests(TestCase):
    def setUp(self):
        self.patient = create_user("hook-patient@example.com", UserType.PATIENT)
        self.doctor = create_user("hook-doctor@example.com", UserType.DOCTOR)
        self.consultation = create_consultation(self.patient, self.doctor)
        self.patient_client = auth_client(self.patient)
        self.doctor_client = auth_client(self.doctor)

    def msg_url(self):
        return f"/api/consultations/{self.consultation.id}/messages/"

    def test_patient_attachment_creates_report_candidate(self):
        file_obj = SimpleUploadedFile("chat-report.jpg", b"binary", content_type="image/jpeg")
        response = self.patient_client.post(
            self.msg_url(),
            {"attachments": [file_obj]},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PatientMedicalReport.objects.count(), 1)

    def test_doctor_attachment_does_not_create_report_candidate(self):
        file_obj = SimpleUploadedFile("doctor-file.jpg", b"binary", content_type="image/jpeg")
        response = self.doctor_client.post(
            self.msg_url(),
            {"attachments": [file_obj]},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PatientMedicalReport.objects.count(), 0)

    def test_report_candidate_failure_does_not_block_message_send(self):
        file_obj = SimpleUploadedFile("report.jpg", b"binary", content_type="image/jpeg")
        with patch(
            "apps.patient_records.services.create_patient_medical_report_from_message_attachment",
            side_effect=RuntimeError("simulated failure"),
        ):
            response = self.patient_client.post(
                self.msg_url(),
                {"attachments": [file_obj]},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
