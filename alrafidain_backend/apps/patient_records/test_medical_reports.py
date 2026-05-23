from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    MedicalReportSource,
    MedicalReportType,
    MedicalReportVisibility,
    MedicalSpecialty,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.messaging.models import ConsultationMessage, MessageAttachment
from apps.patient_records.models import MedicalRecordEntry, PatientMedicalReport
from apps.patient_records.services import (
    create_patient_medical_report_from_message_attachment,
    get_or_create_patient_medical_record,
    process_medical_report_ocr,
)
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile

User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_patient(email="report-patient@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",  # noqa: S106 - test fixture credential
        first_name="Pat",
        last_name="Ient",
        user_type=UserType.PATIENT,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def create_doctor(email="report-doctor@example.com", approved=True):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",  # noqa: S106 - test fixture credential
        first_name="Doc",
        last_name="Tor",
        user_type=UserType.DOCTOR,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.INTERNAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
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


class PatientMedicalReportModelTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.other_patient = create_patient("other-report-patient@example.com")
        self.doctor = create_doctor()
        self.consultation = create_consultation(self.patient, self.doctor)

    def _create_message_and_attachment(self, sender):
        message = ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=sender,
            sender_role="patient" if sender.user_type == UserType.PATIENT else "doctor",
            body="attachment message",
        )
        attachment = MessageAttachment.objects.create(
            message=message,
            file=SimpleUploadedFile("report.jpg", b"binary", content_type="image/jpeg"),
            original_name="report.jpg",
            uploaded_by=sender,
        )
        return message, attachment

    def test_requires_patient_user(self):
        report = PatientMedicalReport(
            patient=self.doctor,
            title="Bad owner",
        )
        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_consultation_patient_must_match_report_patient(self):
        report = PatientMedicalReport(
            patient=self.other_patient,
            consultation=self.consultation,
            title="Mismatch",
        )
        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_source_message_must_match_consultation(self):
        message, _ = self._create_message_and_attachment(self.patient)
        other_consultation = create_consultation(self.other_patient, self.doctor)
        report = PatientMedicalReport(
            patient=self.patient,
            consultation=other_consultation,
            source_message=message,
            title="Mismatch",
        )
        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_source_attachment_must_match_source_message(self):
        message_1, _ = self._create_message_and_attachment(self.patient)
        message_2, attachment_2 = self._create_message_and_attachment(self.patient)
        report = PatientMedicalReport(
            patient=self.patient,
            consultation=self.consultation,
            source_message=message_1,
            source_attachment=attachment_2,
            title="Mismatch",
        )
        with self.assertRaises(ValidationError):
            report.full_clean()
        self.assertNotEqual(message_1.id, message_2.id)

    def test_duplicate_source_attachment_is_rejected(self):
        message, attachment = self._create_message_and_attachment(self.patient)
        PatientMedicalReport.objects.create(
            patient=self.patient,
            consultation=self.consultation,
            source_message=message,
            source_attachment=attachment,
            title="First",
        )
        with self.assertRaises(IntegrityError):
            PatientMedicalReport.objects.create(
                patient=self.patient,
                consultation=self.consultation,
                source_message=message,
                source_attachment=attachment,
                title="Second",
            )

    def test_not_medical_report_forces_false_flag(self):
        report = PatientMedicalReport(
            patient=self.patient,
            consultation=self.consultation,
            report_type=MedicalReportType.NOT_MEDICAL_REPORT,
            is_medical_report=True,
            title="Rejected",
        )
        report.full_clean()
        self.assertFalse(report.is_medical_report)


class PatientMedicalReportServiceTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.consultation = create_consultation(self.patient, self.doctor)

    def _create_message_attachment(self, sender, filename="report.jpg", content_type="image/jpeg"):
        message = ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=sender,
            sender_role="patient" if sender.user_type == UserType.PATIENT else "doctor",
            body="message",
        )
        attachment = MessageAttachment.objects.create(
            message=message,
            file=SimpleUploadedFile(filename, b"binary", content_type=content_type),
            original_name=filename,
            uploaded_by=sender,
        )
        return attachment

    def test_patient_chat_attachment_creates_report_candidate(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        self.assertIsNotNone(report)
        self.assertEqual(report.source, MedicalReportSource.CHAT_ATTACHMENT)
        self.assertEqual(report.source_attachment_id, attachment.id)

    def test_doctor_chat_attachment_does_not_create_report_candidate(self):
        attachment = self._create_message_attachment(self.doctor)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        self.assertIsNone(report)

    def test_unsupported_extension_is_skipped(self):
        attachment = self._create_message_attachment(
            self.patient,
            filename="report.exe",
            content_type="application/octet-stream",
        )
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        self.assertIsNone(report)

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_accepted_text_updates_report(self, mock_extract, mock_secure):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        mock_extract.return_value = "lab report text"
        mock_secure.return_value = {
            "accepted": True,
            "reason": "ok",
            "sanitized_text": "cleaned report text",
            "is_medical_report": True,
            "has_prompt_injection": False,
        }

        processed = process_medical_report_ocr(report=report)
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, "ocr_completed")
        self.assertTrue(processed.is_medical_report)
        self.assertEqual(processed.raw_ocr_text, "lab report text")
        self.assertEqual(processed.cleaned_report_text, "cleaned report text")
        self.assertIsNotNone(processed.processed_at)

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_rejected_not_medical(self, mock_extract, mock_secure):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        mock_extract.return_value = "spam text"
        mock_secure.return_value = {
            "accepted": False,
            "reason": "not_medical_report",
            "sanitized_text": "",
            "is_medical_report": False,
            "has_prompt_injection": False,
        }

        processed = process_medical_report_ocr(report=report)
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, "rejected")
        self.assertFalse(processed.is_medical_report)
        self.assertEqual(processed.rejection_reason, "not_medical_report")
        self.assertEqual(processed.report_type, MedicalReportType.NOT_MEDICAL_REPORT)

    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_empty_extraction_rejected_without_crash(self, mock_extract):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        mock_extract.return_value = ""

        processed = process_medical_report_ocr(report=report)
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, "rejected")
        self.assertFalse(processed.is_medical_report)
        self.assertEqual(processed.rejection_reason, "empty_ocr_text")

    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_exception_marks_failed_without_raising(self, mock_extract):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        mock_extract.side_effect = RuntimeError("ocr failure")

        processed = process_medical_report_ocr(report=report)
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, "failed")
        self.assertIn("ocr failure", processed.processing_error)

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_force_false_does_not_reprocess_completed_report(self, mock_extract, mock_secure):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.processing_status = "ocr_completed"
        report.raw_ocr_text = "existing"
        report.cleaned_report_text = "existing-cleaned"
        report.save(
            update_fields=[
                "processing_status",
                "raw_ocr_text",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        processed = process_medical_report_ocr(report=report, force=False)
        processed.refresh_from_db()

        self.assertEqual(processed.raw_ocr_text, "existing")
        mock_extract.assert_not_called()
        mock_secure.assert_not_called()

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_force_true_reprocesses_completed_report(self, mock_extract, mock_secure):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.processing_status = "ocr_completed"
        report.raw_ocr_text = "existing"
        report.cleaned_report_text = "existing-cleaned"
        report.save(
            update_fields=[
                "processing_status",
                "raw_ocr_text",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        mock_extract.return_value = "new raw text"
        mock_secure.return_value = {
            "accepted": True,
            "reason": "ok",
            "sanitized_text": "new cleaned text",
            "is_medical_report": True,
            "has_prompt_injection": False,
        }

        processed = process_medical_report_ocr(report=report, force=True)
        processed.refresh_from_db()

        self.assertEqual(processed.raw_ocr_text, "new raw text")
        self.assertEqual(processed.cleaned_report_text, "new cleaned text")
        mock_extract.assert_called_once()


class PatientMedicalReportAPITests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.patient2 = create_patient("patient-two@example.com")
        self.doctor = create_doctor()
        self.doctor2 = create_doctor("doctor-two@example.com")
        self.consultation = create_consultation(self.patient, self.doctor)

        self.patient_client = auth_client(self.patient)
        self.patient2_client = auth_client(self.patient2)
        self.doctor_client = auth_client(self.doctor)
        self.doctor2_client = auth_client(self.doctor2)

        self.message = ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=self.patient,
            sender_role="patient",
            body="message",
        )
        self.attachment = MessageAttachment.objects.create(
            message=self.message,
            file=SimpleUploadedFile("report.jpg", b"binary", content_type="image/jpeg"),
            original_name="report.jpg",
            uploaded_by=self.patient,
        )
        self.report = PatientMedicalReport.objects.create(
            patient=self.patient,
            consultation=self.consultation,
            source_message=self.message,
            source_attachment=self.attachment,
            title="Initial report",
            raw_ocr_text="internal raw text",
            cleaned_report_text="cleaned",
            visibility=MedicalReportVisibility.PATIENT_AND_ASSIGNED_DOCTOR,
        )

    def test_patient_can_list_own_reports(self):
        response = self.patient_client.get("/api/patient/medical-reports/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

    def test_patient_cannot_list_another_patient_reports(self):
        response = self.patient2_client.get("/api/patient/medical-reports/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 0)

    def test_assigned_doctor_can_list_consultation_reports(self):
        response = self.doctor_client.get(
            f"/api/doctor/consultations/{self.consultation.id}/medical-reports/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

    def test_unassigned_doctor_cannot_list_consultation_reports(self):
        response = self.doctor2_client.get(
            f"/api/doctor/consultations/{self.consultation.id}/medical-reports/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assigned_doctor_can_view_detail(self):
        response = self.doctor_client.get(f"/api/doctor/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("raw_ocr_text", response.data["data"])

    def test_patient_can_view_own_detail_without_raw_text(self):
        response = self.patient_client.get(f"/api/patient/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("raw_ocr_text", response.data["data"])

    def test_doctor_can_mark_report_reviewed(self):
        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/review/",
            {"doctor_notes": "Reviewed and accepted", "is_medical_report": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.report.refresh_from_db()
        self.assertEqual(self.report.reviewed_by_id, self.doctor.id)

    def test_patient_cannot_mark_report_reviewed(self):
        response = self.patient_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/review/",
            {"doctor_notes": "try"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_detail_does_not_expose_local_file_paths(self):
        response = self.doctor_client.get(f"/api/doctor/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        source_attachment = response.data["data"].get("source_attachment") or {}
        file_url = source_attachment.get("file_url", "")
        self.assertNotIn("/home/", file_url)

    def test_report_detail_does_not_include_audit_internals(self):
        response = self.doctor_client.get(f"/api/doctor/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("audit", response.data["data"])

    def test_linked_entry_summary_is_safe(self):
        record = get_or_create_patient_medical_record(self.patient)
        entry = MedicalRecordEntry.objects.create(
            medical_record=record,
            category="general_note",
            title="Note",
            value="Value",
            source_role="patient",
            source_user=self.patient,
        )
        self.report.linked_medical_record_entry = entry
        self.report.save(update_fields=["linked_medical_record_entry", "updated_at"])

        response = self.doctor_client.get(f"/api/doctor/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        linked = response.data["data"]["linked_medical_record_entry"]
        self.assertEqual(linked["id"], str(entry.id))
        self.assertEqual(linked["title"], "Note")

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_assigned_doctor_can_trigger_process_ocr(self, mock_extract, mock_secure):
        mock_extract.return_value = "ocr raw"
        mock_secure.return_value = {
            "accepted": True,
            "reason": "ok",
            "sanitized_text": "ocr cleaned",
            "is_medical_report": True,
            "has_prompt_injection": False,
        }
        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/process-ocr/",
            {"force": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["processing_status"], "ocr_completed")

    def test_unassigned_doctor_cannot_trigger_process_ocr(self):
        response = self.doctor2_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/process-ocr/",
            {"force": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_trigger_process_ocr(self):
        response = self.patient_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/process-ocr/",
            {"force": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_process_ocr_response_is_safe_for_doctor_detail(self, mock_extract, mock_secure):
        mock_extract.return_value = "raw"
        mock_secure.return_value = {
            "accepted": False,
            "reason": "not_medical_report",
            "sanitized_text": "",
            "is_medical_report": False,
            "has_prompt_injection": False,
        }
        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/process-ocr/",
            {"force": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        source_attachment = response.data["data"].get("source_attachment") or {}
        file_url = source_attachment.get("file_url", "")
        self.assertNotIn("/home/", file_url)

    @patch("apps.patient_records.services.extract_clinical_report_text")
    @override_settings(CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD=True, CLINICAL_REPORT_OCR_ON_UPLOAD=True)
    def test_patient_detail_does_not_expose_internal_processing_error(self, mock_extract):
        mock_extract.side_effect = RuntimeError("internal ocr issue")
        self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/process-ocr/",
            {"force": True},
            format="json",
        )

        response = self.patient_client.get(f"/api/patient/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("processing_error", response.data["data"])
