from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    MedicalRecordVerificationStatus,
    MedicalReportProcessingStatus,
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
    classify_medical_report_with_llm,
    create_patient_medical_report_from_message_attachment,
    get_or_create_patient_medical_record,
    medical_report_type_to_record_category,
    process_medical_report_ocr,
    save_medical_report_to_patient_record,
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

    def _create_llm_completed_report(
        self,
        *,
        report_type=MedicalReportType.LAB_REPORT,
        cleaned_report_text="Hemoglobin 13.5 g/dL",
        is_medical_report=True,
    ):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.report_type = report_type
        report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        report.is_medical_report = is_medical_report
        report.cleaned_report_text = cleaned_report_text
        report.structured_payload = {
            "structured_data": {"lab_values": [{"name": "Hemoglobin", "value": "13.5"}]}
        }
        report.llm_confidence = 0.9100
        report.detected_language = "arabic"
        report.removed_noise_summary = ["phone number"]
        report.save(
            update_fields=[
                "report_type",
                "processing_status",
                "is_medical_report",
                "cleaned_report_text",
                "structured_payload",
                "llm_confidence",
                "detected_language",
                "removed_noise_summary",
                "updated_at",
            ]
        )
        return report

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

    def test_llm_accepted_lab_report_updates_fields(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "Hemoglobin 13.5 g/dL"
        report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": (
                        '{"is_medical_report": true, "report_type": "lab_report", '
                        '"detected_language": "arabic", "confidence": 0.91, '
                        '"title": "CBC laboratory report", "cleaned_report_text": '
                        '"Hemoglobin 13.5 g/dL", "removed_noise_summary": '
                        '["laboratory address", "phone numbers"], "structured_data": '
                        '{"sections": [{"name": "CBC", "content": "..."}]}, '
                        '"safety": {"contains_diagnosis_claim": false, '
                        '"contains_prescription_instruction": false, '
                        '"contains_prompt_injection": false, "notes": []}}'
                    ),
                    "model": "deepseek-chat",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "raw": {"ok": True},
                }

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.LLM_COMPLETED)
        self.assertTrue(processed.is_medical_report)
        self.assertEqual(processed.report_type, MedicalReportType.LAB_REPORT)
        self.assertEqual(processed.cleaned_report_text, "Hemoglobin 13.5 g/dL")
        self.assertEqual(len(processed.removed_noise_summary), 2)
        self.assertEqual(float(processed.llm_confidence), 0.91)
        self.assertIn("structured_data", processed.structured_payload)
        self.assertIn("llm", processed.structured_payload)

    def test_llm_rejects_not_medical_report(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "This is random poster text"
        report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": (
                        '{"is_medical_report": false, "report_type": "not_medical_report", '
                        '"detected_language": "english", "confidence": 0.93, '
                        '"title": "", "cleaned_report_text": "", '
                        '"removed_noise_summary": ["ad text"], "structured_data": {}, '
                        '"safety": {"contains_diagnosis_claim": false, '
                        '"contains_prescription_instruction": false, '
                        '"contains_prompt_injection": false, "notes": []}}'
                    ),
                    "model": "deepseek-chat",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "raw": {"ok": True},
                }

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.REJECTED)
        self.assertFalse(processed.is_medical_report)
        self.assertEqual(processed.report_type, MedicalReportType.NOT_MEDICAL_REPORT)
        self.assertEqual(processed.rejection_reason, "llm_not_medical_report")

    @override_settings(CLINICAL_REPORT_LLM_MIN_CONFIDENCE=0.60)
    def test_llm_low_confidence_rejected(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "Potential report text"
        report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": (
                        '{"is_medical_report": true, "report_type": "lab_report", '
                        '"detected_language": "english", "confidence": 0.42, '
                        '"title": "", "cleaned_report_text": "x", '
                        '"removed_noise_summary": [], "structured_data": {}, '
                        '"safety": {"contains_diagnosis_claim": false, '
                        '"contains_prescription_instruction": false, '
                        '"contains_prompt_injection": false, "notes": []}}'
                    ),
                    "model": "deepseek-chat",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "raw": {"ok": True},
                }

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()

        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.REJECTED)
        self.assertEqual(processed.report_type, MedicalReportType.UNKNOWN)
        self.assertEqual(processed.rejection_reason, "low_llm_confidence")

    def test_llm_invalid_json_fails_safely(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "Potential report text"
        report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": "not json",
                    "model": "deepseek-chat",
                    "usage": {},
                    "raw": {"ok": True},
                }

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()
        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.FAILED)
        self.assertIn("Invalid LLM classification response", processed.processing_error)

    def test_llm_exception_fails_safely(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "Potential report text"
        report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                raise RuntimeError("llm timeout")

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()
        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.FAILED)
        self.assertIn("llm timeout", processed.processing_error)

    def test_llm_no_ocr_text_fails_safely(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = ""
        report.cleaned_report_text = ""
        report.save(update_fields=["raw_ocr_text", "cleaned_report_text", "updated_at"])

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": "{}",
                    "model": "deepseek-chat",
                    "usage": {},
                    "raw": {},
                }

        processed = classify_medical_report_with_llm(report=report, llm_client=StubLLMClient())
        processed.refresh_from_db()
        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.FAILED)
        self.assertIn("No OCR text available", processed.processing_error)

    def test_llm_force_false_skips_completed(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        report.llm_confidence = 0.8500
        report.cleaned_report_text = "existing"
        report.save(
            update_fields=[
                "processing_status",
                "llm_confidence",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        class StubLLMClient:
            called = False

            def chat(self, messages, temperature=0.0, max_tokens=4000):
                self.called = True
                return {}

        client = StubLLMClient()
        processed = classify_medical_report_with_llm(report=report, llm_client=client, force=False)
        processed.refresh_from_db()
        self.assertFalse(client.called)
        self.assertEqual(processed.cleaned_report_text, "existing")

    def test_llm_force_true_reprocesses(self):
        attachment = self._create_message_attachment(self.patient)
        report = create_patient_medical_report_from_message_attachment(attachment=attachment)
        report.raw_ocr_text = "Potential report text"
        report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        report.llm_confidence = 0.8500
        report.cleaned_report_text = "existing"
        report.save(
            update_fields=[
                "raw_ocr_text",
                "processing_status",
                "llm_confidence",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        class StubLLMClient:
            def chat(self, messages, temperature=0.0, max_tokens=4000):
                return {
                    "content": (
                        '{"is_medical_report": true, "report_type": "lab_report", '
                        '"detected_language": "english", "confidence": 0.88, '
                        '"title": "New title", "cleaned_report_text": "new cleaned", '
                        '"removed_noise_summary": [], "structured_data": {}, '
                        '"safety": {"contains_diagnosis_claim": false, '
                        '"contains_prescription_instruction": false, '
                        '"contains_prompt_injection": false, "notes": []}}'
                    ),
                    "model": "deepseek-chat",
                    "usage": {},
                    "raw": {},
                }

        processed = classify_medical_report_with_llm(
            report=report,
            llm_client=StubLLMClient(),
            force=True,
        )
        processed.refresh_from_db()
        self.assertEqual(processed.cleaned_report_text, "new cleaned")
        self.assertEqual(processed.report_type, MedicalReportType.LAB_REPORT)

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=False, CLINICAL_REPORT_LLM_SYNC_AFTER_OCR=False)
    @patch("apps.patient_records.services.classify_medical_report_with_llm")
    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_accepted_with_llm_auto_disabled_stays_ocr_completed(
        self,
        mock_extract,
        mock_secure,
        mock_classify,
    ):
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
        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.OCR_COMPLETED)
        mock_classify.assert_not_called()

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True, CLINICAL_REPORT_LLM_SYNC_AFTER_OCR=True)
    @patch("apps.patient_records.services.classify_medical_report_with_llm")
    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_ocr_accepted_with_llm_auto_enabled_calls_classifier(
        self,
        mock_extract,
        mock_secure,
        mock_classify,
    ):
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

        process_medical_report_ocr(report=report)
        mock_classify.assert_called_once()

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True, CLINICAL_REPORT_LLM_SYNC_AFTER_OCR=True)
    @patch(
        "apps.patient_records.services.classify_medical_report_with_llm",
        side_effect=RuntimeError("llm fail"),
    )
    @patch("apps.patient_records.services.secure_extracted_report_text")
    @patch("apps.patient_records.services.extract_clinical_report_text")
    def test_llm_failure_after_ocr_does_not_crash_ocr_process(
        self,
        mock_extract,
        mock_secure,
        _mock_classify,
    ):
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
        self.assertEqual(processed.processing_status, MedicalReportProcessingStatus.OCR_COMPLETED)

    def test_medical_report_type_mapping_lab_report(self):
        self.assertEqual(medical_report_type_to_record_category("lab_report"), "lab_report")

    def test_medical_report_type_mapping_sonar_report(self):
        self.assertEqual(medical_report_type_to_record_category("sonar_report"), "sonar_report")

    def test_medical_report_type_mapping_xray_report(self):
        self.assertEqual(medical_report_type_to_record_category("xray_report"), "xray_report")

    def test_medical_report_type_mapping_ct_and_mri_to_radiology(self):
        self.assertEqual(medical_report_type_to_record_category("ct_scan"), "radiology_report")
        self.assertEqual(medical_report_type_to_record_category("mri"), "radiology_report")

    def test_llm_completed_report_saves_to_medical_record_and_links_entry(self):
        report = self._create_llm_completed_report()
        entry = save_medical_report_to_patient_record(report=report)
        report.refresh_from_db()

        self.assertIsNotNone(entry)
        self.assertEqual(entry.category, "lab_report")
        self.assertEqual(report.linked_medical_record_entry_id, entry.id)
        self.assertEqual(entry.verification_status, MedicalRecordVerificationStatus.SELF_REPORTED)

    def test_not_medical_report_is_not_saved(self):
        report = self._create_llm_completed_report(
            report_type=MedicalReportType.NOT_MEDICAL_REPORT,
            cleaned_report_text="",
            is_medical_report=False,
        )
        with self.assertRaises(ValueError):
            save_medical_report_to_patient_record(report=report)

    def test_report_without_cleaned_text_and_structured_data_fails_safely(self):
        report = self._create_llm_completed_report(cleaned_report_text="")
        report.structured_payload = {}
        report.save(update_fields=["structured_payload", "updated_at"])

        with self.assertRaises(ValueError):
            save_medical_report_to_patient_record(report=report)

    def test_repeated_save_without_force_returns_existing_entry_without_duplicate(self):
        report = self._create_llm_completed_report()
        first_entry = save_medical_report_to_patient_record(report=report)
        second_entry = save_medical_report_to_patient_record(report=report, force=False)

        self.assertEqual(first_entry.id, second_entry.id)
        self.assertEqual(
            MedicalRecordEntry.objects.filter(medical_record__patient=self.patient).count(),
            1,
        )

    def test_force_true_updates_existing_entry(self):
        report = self._create_llm_completed_report(cleaned_report_text="old value")
        entry = save_medical_report_to_patient_record(report=report)
        report.cleaned_report_text = "updated value"
        report.save(update_fields=["cleaned_report_text", "updated_at"])

        updated = save_medical_report_to_patient_record(report=report, force=True)
        updated.refresh_from_db()
        self.assertEqual(updated.id, entry.id)
        self.assertIn("updated value", updated.value)

    def test_confirm_by_doctor_sets_doctor_confirmed_and_verified_fields(self):
        report = self._create_llm_completed_report()
        entry = save_medical_report_to_patient_record(
            report=report,
            doctor=self.doctor,
            confirm_by_doctor=True,
        )
        report.refresh_from_db()
        self.assertEqual(
            entry.verification_status,
            MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
        )
        self.assertEqual(entry.verified_by_id, self.doctor.id)
        self.assertIsNotNone(entry.verified_at)
        self.assertEqual(report.reviewed_by_id, self.doctor.id)

    def test_non_assigned_doctor_cannot_confirm_save(self):
        other_doctor = create_doctor("another-doctor@example.com")
        report = self._create_llm_completed_report()
        with self.assertRaises(PermissionError):
            save_medical_report_to_patient_record(
                report=report,
                doctor=other_doctor,
                confirm_by_doctor=True,
            )

    def test_save_to_record_creates_audit_log(self):
        report = self._create_llm_completed_report()
        entry = save_medical_report_to_patient_record(report=report)

        self.assertTrue(
            AuditLog.objects.filter(
                action="medical_report_saved_to_patient_record",
                target_id=str(entry.id),
            ).exists()
        )


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

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True)
    def test_assigned_doctor_can_post_classify_llm(self):
        self.report.raw_ocr_text = "Hemoglobin 13.5 g/dL"
        self.report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        self.report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        with patch("apps.patient_records.services.DeepSeekClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.chat.return_value = {
                "content": (
                    '{"is_medical_report": true, "report_type": "lab_report", '
                    '"detected_language": "english", "confidence": 0.92, '
                    '"title": "CBC laboratory report", "cleaned_report_text": "cleaned text", '
                    '"removed_noise_summary": ["address"], "structured_data": {}, '
                    '"safety": {"contains_diagnosis_claim": false, '
                    '"contains_prescription_instruction": false, '
                    '"contains_prompt_injection": false, "notes": []}}'
                ),
                "model": "deepseek-chat",
                "usage": {},
                "raw": {"provider": "ok"},
            }

            response = self.doctor_client.post(
                f"/api/doctor/medical-reports/{self.report.id}/classify-llm/",
                {"force": True},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["processing_status"], "llm_completed")

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True)
    def test_unassigned_doctor_cannot_classify_llm(self):
        response = self.doctor2_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/classify-llm/",
            {"force": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True)
    def test_patient_cannot_classify_llm(self):
        response = self.patient_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/classify-llm/",
            {"force": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=False)
    def test_llm_disabled_returns_safe_error(self):
        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/classify-llm/",
            {"force": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(CLINICAL_REPORT_LLM_ENABLED=True)
    def test_classify_llm_response_does_not_expose_provider_payload(self):
        self.report.raw_ocr_text = "Hemoglobin 13.5 g/dL"
        self.report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
        self.report.save(update_fields=["raw_ocr_text", "processing_status", "updated_at"])

        with patch("apps.patient_records.services.DeepSeekClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.chat.return_value = {
                "content": (
                    '{"is_medical_report": true, "report_type": "lab_report", '
                    '"detected_language": "english", "confidence": 0.92, '
                    '"title": "CBC laboratory report", "cleaned_report_text": "cleaned text", '
                    '"removed_noise_summary": ["address"], "structured_data": {}, '
                    '"safety": {"contains_diagnosis_claim": false, '
                    '"contains_prescription_instruction": false, '
                    '"contains_prompt_injection": false, "notes": []}}'
                ),
                "model": "deepseek-chat",
                "usage": {},
                "raw": {"provider": "ok", "prompt": "secret", "raw_response": "secret"},
            }
            response = self.doctor_client.post(
                f"/api/doctor/medical-reports/{self.report.id}/classify-llm/",
                {"force": True},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data["data"].get("structured_payload") or {}
        self.assertNotIn("prompt", payload)
        self.assertNotIn("raw_response", payload)

    def test_assigned_doctor_can_post_save_to_record(self):
        self.report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        self.report.is_medical_report = True
        self.report.report_type = MedicalReportType.LAB_REPORT
        self.report.cleaned_report_text = "Hemoglobin 13.5 g/dL"
        self.report.save(
            update_fields=[
                "processing_status",
                "is_medical_report",
                "report_type",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"force": False, "confirm_by_doctor": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.linked_medical_record_entry_id)

    def test_patient_cannot_post_save_to_record(self):
        response = self.patient_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"force": False, "confirm_by_doctor": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_doctor_cannot_post_save_to_record(self):
        response = self.doctor2_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"force": False, "confirm_by_doctor": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_save_to_record_response_includes_linked_entry_summary(self):
        self.report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        self.report.is_medical_report = True
        self.report.report_type = MedicalReportType.LAB_REPORT
        self.report.cleaned_report_text = "Hemoglobin 13.5 g/dL"
        self.report.save(
            update_fields=[
                "processing_status",
                "is_medical_report",
                "report_type",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"force": False, "confirm_by_doctor": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        linked = response.data["data"]["linked_medical_record_entry"]
        self.assertIn("id", linked)
        self.assertIn("category", linked)
        self.assertIn("verification_status", linked)

    def test_save_to_record_response_does_not_expose_prompt_or_local_paths(self):
        self.report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        self.report.is_medical_report = True
        self.report.report_type = MedicalReportType.LAB_REPORT
        self.report.cleaned_report_text = "Hemoglobin 13.5 g/dL"
        self.report.structured_payload = {
            "llm": {"provider": "deepseek"},
            "raw_provider_payload": {"token": "nope"},
        }
        self.report.save(
            update_fields=[
                "processing_status",
                "is_medical_report",
                "report_type",
                "cleaned_report_text",
                "structured_payload",
                "updated_at",
            ]
        )

        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"force": False, "confirm_by_doctor": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data["data"].get("structured_payload") or {}
        self.assertNotIn("raw_provider_payload", payload)
        source_attachment = response.data["data"].get("source_attachment") or {}
        self.assertNotIn("/home/", source_attachment.get("file_url", ""))

    def test_confirm_by_doctor_request_produces_doctor_confirmed_entry(self):
        self.report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        self.report.is_medical_report = True
        self.report.report_type = MedicalReportType.LAB_REPORT
        self.report.cleaned_report_text = "Hemoglobin 13.5 g/dL"
        self.report.save(
            update_fields=[
                "processing_status",
                "is_medical_report",
                "report_type",
                "cleaned_report_text",
                "updated_at",
            ]
        )

        response = self.doctor_client.post(
            f"/api/doctor/medical-reports/{self.report.id}/save-to-record/",
            {"confirm_by_doctor": True, "doctor_notes": "doctor reviewed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.report.refresh_from_db()
        entry = self.report.linked_medical_record_entry
        self.assertIsNotNone(entry)
        self.assertEqual(
            entry.verification_status,
            MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
        )
        self.assertEqual(entry.verified_by_id, self.doctor.id)
        self.assertEqual(self.report.doctor_notes, "doctor reviewed")

    def test_patient_detail_does_not_expose_raw_ocr_or_processing_error_after_llm(self):
        self.report.raw_ocr_text = "private raw text"
        self.report.processing_error = "internal issue"
        self.report.processing_status = MedicalReportProcessingStatus.FAILED
        self.report.save(
            update_fields=["raw_ocr_text", "processing_error", "processing_status", "updated_at"]
        )

        response = self.patient_client.get(f"/api/patient/medical-reports/{self.report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("raw_ocr_text", response.data["data"])
        self.assertNotIn("processing_error", response.data["data"])
