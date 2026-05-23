import logging
import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    MedicalReportProcessingStatus,
    MedicalReportSource,
    MedicalReportType,
    NotificationType,
    UserType,
    VerificationStatus,
)
from apps.common.policies import ClinicalAccessPolicy
from apps.common.report_extraction import extract_clinical_report_text, secure_extracted_report_text
from apps.notifications.services import create_notification
from apps.rag.llm_clients.deepseek_client import DeepSeekClient

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord, PatientMedicalReport
from .report_llm import (
    build_medical_report_classification_prompt,
    parse_medical_report_llm_response,
    validate_medical_report_llm_payload,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def _is_approved_laboratorian(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.LABORATORIAN:
        return False
    try:
        return user.laboratorian_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def get_or_create_patient_medical_record(patient):
    if not patient or patient.user_type != UserType.PATIENT:
        raise ValueError("Medical records are only available for patient users.")

    record, created = PatientMedicalRecord.objects.get_or_create(patient=patient)
    BloodGroupRecord.objects.get_or_create(medical_record=record)

    if created:
        create_audit_log(
            actor=patient,
            action="medical_record_created",
            target=record,
            metadata={
                "record_id": str(record.id),
                "patient_id": str(patient.id),
                "actor_id": str(patient.id),
            },
        )

    return record


def doctor_can_access_patient_record(doctor, patient) -> bool:
    return ClinicalAccessPolicy.can_doctor_access_patient(doctor, patient)


def create_medical_record_entry(
    record, source_user, category, title, value, notes=None, request=None
):
    if not record or not source_user:
        raise ValueError("Record and source user are required.")

    verified_by = None
    verified_at = None

    if source_user.user_type == UserType.PATIENT:
        if record.patient_id != source_user.id:
            raise PermissionError("Patients can only create entries in their own records.")
        verification_status = MedicalRecordVerificationStatus.SELF_REPORTED
        source_role = MedicalRecordSourceRole.PATIENT
    elif source_user.user_type == UserType.DOCTOR:
        if not doctor_can_access_patient_record(source_user, record.patient):
            raise PermissionError("Doctor cannot access this patient's medical record.")
        verification_status = MedicalRecordVerificationStatus.DOCTOR_CONFIRMED
        source_role = MedicalRecordSourceRole.DOCTOR
        verified_by = source_user
        verified_at = timezone.now()
    else:
        raise PermissionError(
            "Only patient or approved doctor can create generic medical record entries."
        )

    entry = MedicalRecordEntry.objects.create(
        medical_record=record,
        category=category,
        title=title,
        value=value,
        verification_status=verification_status,
        source_user=source_user,
        source_role=source_role,
        verified_by=verified_by,
        verified_at=verified_at,
        notes=notes or "",
    )

    create_audit_log(
        actor=source_user,
        action="medical_record_entry_created",
        target=entry,
        metadata={
            "record_id": str(record.id),
            "entry_id": str(entry.id),
            "patient_id": str(record.patient_id),
            "actor_id": str(source_user.id),
            "category": category,
            "verification_status": verification_status,
        },
        request=request,
    )

    return entry


def confirm_medical_record_entry(entry, doctor, status, notes=None, request=None):
    allowed = {
        MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
        MedicalRecordVerificationStatus.REJECTED,
    }
    if status not in allowed:
        raise ValueError("Invalid confirmation status.")
    if not doctor_can_access_patient_record(doctor, entry.medical_record.patient):
        raise PermissionError("Doctor cannot access this patient's medical record.")

    entry.verification_status = status
    entry.verified_by = doctor
    entry.verified_at = timezone.now()
    if notes:
        entry.notes = notes
    entry.save(
        update_fields=["verification_status", "verified_by", "verified_at", "notes", "updated_at"]
    )

    action = (
        "medical_record_entry_confirmed"
        if status == MedicalRecordVerificationStatus.DOCTOR_CONFIRMED
        else "medical_record_entry_rejected"
    )

    create_audit_log(
        actor=doctor,
        action=action,
        target=entry,
        metadata={
            "record_id": str(entry.medical_record_id),
            "entry_id": str(entry.id),
            "patient_id": str(entry.medical_record.patient_id),
            "actor_id": str(doctor.id),
            "category": entry.category,
            "verification_status": status,
        },
        request=request,
    )

    create_notification(
        recipient=entry.medical_record.patient,
        notification_type=NotificationType.MEDICAL_RECORD,
        title="Medical record entry updated",
        message=(
            "A doctor confirmed one of your medical record entries."
            if status == MedicalRecordVerificationStatus.DOCTOR_CONFIRMED
            else "A doctor rejected one of your medical record entries."
        ),
        data={
            "record_id": str(entry.medical_record_id),
            "entry_id": str(entry.id),
            "verification_status": status,
        },
    )

    return entry


def set_blood_group(record, user, blood_group, notes=None, request=None):
    blood_group_record, _ = BloodGroupRecord.objects.get_or_create(medical_record=record)

    verified_by = None
    verified_at = None

    if user.user_type == UserType.PATIENT:
        if record.patient_id != user.id:
            raise PermissionError("Patients can only set blood group in their own records.")
        verification_status = MedicalRecordVerificationStatus.SELF_REPORTED
        action = "blood_group_updated"
    elif user.user_type == UserType.DOCTOR:
        if not doctor_can_access_patient_record(user, record.patient):
            raise PermissionError("Doctor cannot access this patient's medical record.")
        verification_status = MedicalRecordVerificationStatus.DOCTOR_CONFIRMED
        verified_by = user
        verified_at = timezone.now()
        action = "blood_group_updated"
    elif user.user_type == UserType.LABORATORIAN:
        if not _is_approved_laboratorian(user):
            raise PermissionError("Only approved laboratorians can verify blood group.")
        verification_status = MedicalRecordVerificationStatus.LABORATORY_CONFIRMED
        verified_by = user
        verified_at = timezone.now()
        action = "blood_group_verified"
    else:
        raise PermissionError("This role cannot set blood group.")

    blood_group_record.blood_group = blood_group
    blood_group_record.verification_status = verification_status
    blood_group_record.source_user = user
    blood_group_record.verified_by = verified_by
    blood_group_record.verified_at = verified_at
    if notes is not None:
        blood_group_record.notes = notes
    blood_group_record.save(
        update_fields=[
            "blood_group",
            "verification_status",
            "source_user",
            "verified_by",
            "verified_at",
            "notes",
            "updated_at",
        ]
    )

    create_audit_log(
        actor=user,
        action=action,
        target=blood_group_record,
        metadata={
            "record_id": str(record.id),
            "patient_id": str(record.patient_id),
            "actor_id": str(user.id),
            "category": "blood_group",
            "verification_status": verification_status,
        },
        request=request,
    )

    create_notification(
        recipient=record.patient,
        notification_type=NotificationType.MEDICAL_RECORD,
        title="Blood group record updated",
        message=(
            "Your blood group has been verified by the laboratory."
            if verification_status == MedicalRecordVerificationStatus.LABORATORY_CONFIRMED
            else "Your blood group record has been updated."
        ),
        data={
            "record_id": str(record.id),
            "blood_group": blood_group,
            "verification_status": verification_status,
        },
    )

    return blood_group_record


@transaction.atomic
def deactivate_medical_record_entry(entry, actor, notes=None, request=None):
    entry.is_active = False
    if notes:
        entry.notes = notes
    entry.save(update_fields=["is_active", "notes", "updated_at"])

    create_audit_log(
        actor=actor,
        action="medical_record_entry_deactivated",
        target=entry,
        metadata={
            "record_id": str(entry.medical_record_id),
            "entry_id": str(entry.id),
            "patient_id": str(entry.medical_record.patient_id),
            "actor_id": str(actor.id),
            "category": entry.category,
            "verification_status": entry.verification_status,
        },
        request=request,
    )

    return entry


def _is_supported_clinical_attachment(attachment) -> bool:
    allowed_extensions = {
        ext.lower() for ext in getattr(settings, "CLINICAL_ATTACHMENT_ALLOWED_EXTENSIONS", [])
    }
    allowed_content_types = {
        ctype.lower()
        for ctype in getattr(settings, "CLINICAL_ATTACHMENT_ALLOWED_CONTENT_TYPES", [])
    }

    filename = getattr(attachment, "original_name", "") or getattr(attachment.file, "name", "")
    extension = os.path.splitext(filename)[1].lower()
    if extension and allowed_extensions and extension not in allowed_extensions:
        return False

    content_type = ""
    file_obj = getattr(attachment.file, "file", None)
    if file_obj is not None:
        content_type = getattr(file_obj, "content_type", "") or ""
    content_type = content_type.lower()

    return not (
        content_type and allowed_content_types and content_type not in allowed_content_types
    )


def _safe_processing_error(exc: Exception) -> str:
    message = (str(exc) or exc.__class__.__name__).strip()
    if not message:
        message = "Unexpected OCR processing error."
    return message[:300]


def _resolve_report_source_file(report):
    source_attachment = getattr(report, "source_attachment", None)
    if source_attachment and getattr(source_attachment, "file", None):
        return source_attachment.file

    if getattr(report, "original_file", None):
        return report.original_file

    return None


def _build_ocr_payload(*, accepted: bool, gate_payload: dict) -> dict:
    return {
        "ocr": {
            "accepted": accepted,
            "reason": gate_payload.get("reason", "unknown"),
            "has_prompt_injection": bool(gate_payload.get("has_prompt_injection", False)),
            "is_medical_report": bool(gate_payload.get("is_medical_report", False)),
            "extractor": "existing_report_extraction",
            "phase": "10B",
        }
    }


def _build_llm_payload(*, accepted: bool, reason: str, confidence: float, model_name: str) -> dict:
    return {
        "llm": {
            "accepted": accepted,
            "reason": reason,
            "confidence": confidence,
            "provider": "deepseek",
            "model": model_name,
            "phase": "10C",
        }
    }


def _source_attachment_id(report):
    return str(report.source_attachment_id) if report.source_attachment_id else None


def _consultation_id(report):
    return str(report.consultation_id) if report.consultation_id else None


def _get_ocr_input_text(report) -> str:
    cleaned = (report.cleaned_report_text or "").strip()
    if cleaned:
        return cleaned
    return (report.raw_ocr_text or "").strip()


def _save_report_classification_state(report):
    report.save(
        update_fields=[
            "is_medical_report",
            "report_type",
            "title",
            "cleaned_report_text",
            "removed_noise_summary",
            "structured_payload",
            "detected_language",
            "llm_confidence",
            "processing_status",
            "rejection_reason",
            "processing_error",
            "processed_at",
            "updated_at",
        ]
    )


def classify_medical_report_with_llm(*, report, request=None, force=False, llm_client=None):
    if (
        report.processing_status == MedicalReportProcessingStatus.LLM_COMPLETED
        and report.llm_confidence is not None
        and not force
    ):
        return report

    source_text = _get_ocr_input_text(report)
    if not source_text:
        report.processing_status = MedicalReportProcessingStatus.FAILED
        report.processing_error = "No OCR text available for LLM classification."
        report.processed_at = timezone.now()
        _save_report_classification_state(report)
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_llm_failed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": _consultation_id(report),
                "source_attachment_id": _source_attachment_id(report),
                "old_status": report.processing_status,
                "new_status": report.processing_status,
                "report_type": report.report_type,
                "confidence": 0,
                "rejection_reason": "",
                "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": len(report.cleaned_report_text or ""),
                "removed_noise_count": len(report.removed_noise_summary or []),
                "llm_provider": "deepseek",
                "llm_model": getattr(settings, "CLINICAL_REPORT_LLM_MODEL", "deepseek-chat"),
            },
            request=request,
        )
        return report

    old_status = report.processing_status
    report.processing_status = MedicalReportProcessingStatus.LLM_PENDING
    report.processing_error = ""
    report.save(update_fields=["processing_status", "processing_error", "updated_at"])

    model_name = getattr(settings, "CLINICAL_REPORT_LLM_MODEL", "deepseek-chat")
    create_audit_log(
        actor=request.user if request else None,
        action="medical_report_llm_started",
        target=report,
        metadata={
            "report_id": str(report.id),
            "patient_id": str(report.patient_id),
            "consultation_id": _consultation_id(report),
            "source_attachment_id": _source_attachment_id(report),
            "old_status": old_status,
            "new_status": report.processing_status,
            "report_type": report.report_type,
            "confidence": 0,
            "rejection_reason": "",
            "raw_ocr_text_length": len(report.raw_ocr_text or ""),
            "cleaned_text_length": len(report.cleaned_report_text or ""),
            "removed_noise_count": len(report.removed_noise_summary or []),
            "llm_provider": "deepseek",
            "llm_model": model_name,
        },
        request=request,
    )

    try:
        messages = build_medical_report_classification_prompt(report)
        if llm_client is None:
            llm_client = DeepSeekClient(
                model=model_name,
                timeout=int(getattr(settings, "CLINICAL_REPORT_LLM_TIMEOUT_SECONDS", 30)),
            )

        llm_result = llm_client.chat(
            messages,
            temperature=0.0,
            max_tokens=int(getattr(settings, "CLINICAL_REPORT_LLM_MAX_OUTPUT_CHARS", 4000)),
        )
        raw_content = llm_result.get("content") or ""
        parsed = parse_medical_report_llm_response(raw_content)
        payload = validate_medical_report_llm_payload(parsed)

        confidence = float(payload.get("confidence", 0.0))
        min_confidence = float(getattr(settings, "CLINICAL_REPORT_LLM_MIN_CONFIDENCE", 0.60))
        llm_metadata = _build_llm_payload(
            accepted=bool(payload.get("is_medical_report", False)),
            reason="ok",
            confidence=confidence,
            model_name=llm_result.get("model", model_name),
        )

        report.structured_payload = {
            **(report.structured_payload or {}),
            **llm_metadata,
            "structured_data": payload.get("structured_data", {}),
            "safety": payload.get("safety", {}),
        }
        report.detected_language = payload.get("detected_language", "")
        report.llm_confidence = Decimal(f"{confidence:.4f}")
        report.processed_at = timezone.now()
        report.processing_error = ""

        if not payload.get("is_medical_report", False):
            report.is_medical_report = False
            report.report_type = MedicalReportType.NOT_MEDICAL_REPORT
            report.processing_status = MedicalReportProcessingStatus.REJECTED
            report.rejection_reason = "llm_not_medical_report"
            report.cleaned_report_text = ""
            report.removed_noise_summary = payload.get("removed_noise_summary", [])
            _save_report_classification_state(report)
            create_audit_log(
                actor=request.user if request else None,
                action="medical_report_llm_rejected",
                target=report,
                metadata={
                    "report_id": str(report.id),
                    "patient_id": str(report.patient_id),
                    "consultation_id": _consultation_id(report),
                    "source_attachment_id": _source_attachment_id(report),
                    "old_status": old_status,
                    "new_status": report.processing_status,
                    "report_type": report.report_type,
                    "confidence": confidence,
                    "rejection_reason": report.rejection_reason,
                    "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                    "cleaned_text_length": len(report.cleaned_report_text or ""),
                    "removed_noise_count": len(report.removed_noise_summary or []),
                    "llm_provider": "deepseek",
                    "llm_model": llm_result.get("model", model_name),
                },
                request=request,
            )
            return report

        if confidence < min_confidence:
            report.is_medical_report = False
            report.report_type = MedicalReportType.UNKNOWN
            report.processing_status = MedicalReportProcessingStatus.REJECTED
            report.rejection_reason = "low_llm_confidence"
            report.cleaned_report_text = ""
            report.removed_noise_summary = payload.get("removed_noise_summary", [])
            _save_report_classification_state(report)
            create_audit_log(
                actor=request.user if request else None,
                action="medical_report_llm_rejected",
                target=report,
                metadata={
                    "report_id": str(report.id),
                    "patient_id": str(report.patient_id),
                    "consultation_id": _consultation_id(report),
                    "source_attachment_id": _source_attachment_id(report),
                    "old_status": old_status,
                    "new_status": report.processing_status,
                    "report_type": report.report_type,
                    "confidence": confidence,
                    "rejection_reason": report.rejection_reason,
                    "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                    "cleaned_text_length": len(report.cleaned_report_text or ""),
                    "removed_noise_count": len(report.removed_noise_summary or []),
                    "llm_provider": "deepseek",
                    "llm_model": llm_result.get("model", model_name),
                },
                request=request,
            )
            return report

        report.is_medical_report = True
        report.report_type = payload.get("report_type", MedicalReportType.UNKNOWN)
        if payload.get("title"):
            report.title = payload["title"]
        report.cleaned_report_text = payload.get("cleaned_report_text", "")
        report.removed_noise_summary = payload.get("removed_noise_summary", [])
        report.processing_status = MedicalReportProcessingStatus.LLM_COMPLETED
        report.rejection_reason = ""
        _save_report_classification_state(report)
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_llm_completed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": _consultation_id(report),
                "source_attachment_id": _source_attachment_id(report),
                "old_status": old_status,
                "new_status": report.processing_status,
                "report_type": report.report_type,
                "confidence": confidence,
                "rejection_reason": "",
                "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": len(report.cleaned_report_text or ""),
                "removed_noise_count": len(report.removed_noise_summary or []),
                "llm_provider": "deepseek",
                "llm_model": llm_result.get("model", model_name),
            },
            request=request,
        )
        return report
    except ValueError:
        report.processing_status = MedicalReportProcessingStatus.FAILED
        report.processing_error = "Invalid LLM classification response."
        report.processed_at = timezone.now()
        _save_report_classification_state(report)
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_llm_failed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": _consultation_id(report),
                "source_attachment_id": _source_attachment_id(report),
                "old_status": old_status,
                "new_status": report.processing_status,
                "report_type": report.report_type,
                "confidence": float(report.llm_confidence or 0),
                "rejection_reason": report.rejection_reason,
                "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": len(report.cleaned_report_text or ""),
                "removed_noise_count": len(report.removed_noise_summary or []),
                "llm_provider": "deepseek",
                "llm_model": model_name,
            },
            request=request,
        )
        return report
    except Exception as exc:
        report.processing_status = MedicalReportProcessingStatus.FAILED
        report.processing_error = _safe_processing_error(exc)
        report.processed_at = timezone.now()
        _save_report_classification_state(report)
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_llm_failed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": _consultation_id(report),
                "source_attachment_id": _source_attachment_id(report),
                "old_status": old_status,
                "new_status": report.processing_status,
                "report_type": report.report_type,
                "confidence": float(report.llm_confidence or 0),
                "rejection_reason": report.rejection_reason,
                "raw_ocr_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": len(report.cleaned_report_text or ""),
                "removed_noise_count": len(report.removed_noise_summary or []),
                "llm_provider": "deepseek",
                "llm_model": model_name,
            },
            request=request,
        )
        logger.exception(
            "Medical report LLM classification failed",
            extra={"report_id": str(report.id)},
        )
        return report


def classify_medical_report_with_llm_by_id(report_id, request=None, force=False, llm_client=None):
    report = PatientMedicalReport.objects.select_related(
        "source_attachment",
        "source_message",
        "consultation",
    ).get(id=report_id)
    return classify_medical_report_with_llm(
        report=report,
        request=request,
        force=force,
        llm_client=llm_client,
    )


def process_medical_report_ocr(*, report, request=None, force=False):
    if (
        report.processing_status == MedicalReportProcessingStatus.OCR_COMPLETED
        and bool(report.raw_ocr_text)
        and not force
    ):
        return report

    source_file = _resolve_report_source_file(report)
    now = timezone.now()

    if source_file is None:
        report.processing_status = MedicalReportProcessingStatus.FAILED
        report.processing_error = "No source file available for OCR."
        report.processed_at = now
        report.save(
            update_fields=[
                "processing_status",
                "processing_error",
                "processed_at",
                "updated_at",
            ]
        )
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_ocr_failed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
                "source_attachment_id": (
                    str(report.source_attachment_id) if report.source_attachment_id else None
                ),
                "processing_status": report.processing_status,
                "rejection_reason": "",
                "has_prompt_injection": False,
                "is_medical_report": False,
                "raw_text_length": 0,
                "cleaned_text_length": 0,
            },
            request=request,
        )
        return report

    report.processing_status = MedicalReportProcessingStatus.OCR_PENDING
    report.processing_error = ""
    report.save(update_fields=["processing_status", "processing_error", "updated_at"])
    create_audit_log(
        actor=request.user if request else None,
        action="medical_report_ocr_started",
        target=report,
        metadata={
            "report_id": str(report.id),
            "patient_id": str(report.patient_id),
            "consultation_id": str(report.consultation_id) if report.consultation_id else None,
            "source_attachment_id": (
                str(report.source_attachment_id) if report.source_attachment_id else None
            ),
            "processing_status": report.processing_status,
            "rejection_reason": "",
            "has_prompt_injection": False,
            "is_medical_report": False,
            "raw_text_length": 0,
            "cleaned_text_length": 0,
        },
        request=request,
    )

    try:
        raw_text = extract_clinical_report_text(source_file)
        report.raw_ocr_text = raw_text or ""

        if not raw_text:
            report.cleaned_report_text = ""
            report.is_medical_report = False
            report.report_type = MedicalReportType.UNKNOWN
            report.processing_status = MedicalReportProcessingStatus.REJECTED
            report.rejection_reason = "empty_ocr_text"
            report.processing_error = ""
            report.structured_payload = {
                **(report.structured_payload or {}),
                **_build_ocr_payload(
                    accepted=False,
                    gate_payload={
                        "reason": "empty_ocr_text",
                        "has_prompt_injection": False,
                        "is_medical_report": False,
                    },
                ),
            }
            report.processed_at = now
            report.save(
                update_fields=[
                    "raw_ocr_text",
                    "cleaned_report_text",
                    "is_medical_report",
                    "report_type",
                    "processing_status",
                    "rejection_reason",
                    "processing_error",
                    "structured_payload",
                    "processed_at",
                    "updated_at",
                ]
            )
            create_audit_log(
                actor=request.user if request else None,
                action="medical_report_ocr_rejected",
                target=report,
                metadata={
                    "report_id": str(report.id),
                    "patient_id": str(report.patient_id),
                    "consultation_id": (
                        str(report.consultation_id) if report.consultation_id else None
                    ),
                    "source_attachment_id": (
                        str(report.source_attachment_id) if report.source_attachment_id else None
                    ),
                    "processing_status": report.processing_status,
                    "rejection_reason": report.rejection_reason,
                    "has_prompt_injection": False,
                    "is_medical_report": False,
                    "raw_text_length": 0,
                    "cleaned_text_length": 0,
                },
                request=request,
            )
            return report

        secure_payload = secure_extracted_report_text(raw_text)
        report.processed_at = now
        report.processing_error = ""
        report.structured_payload = {
            **(report.structured_payload or {}),
            **_build_ocr_payload(
                accepted=bool(secure_payload.get("accepted", False)),
                gate_payload=secure_payload,
            ),
        }

        if secure_payload.get("accepted"):
            report.cleaned_report_text = secure_payload.get("sanitized_text", "") or ""
            report.is_medical_report = True
            report.processing_status = MedicalReportProcessingStatus.OCR_COMPLETED
            report.rejection_reason = ""
            report.save(
                update_fields=[
                    "raw_ocr_text",
                    "cleaned_report_text",
                    "is_medical_report",
                    "processing_status",
                    "rejection_reason",
                    "processing_error",
                    "structured_payload",
                    "processed_at",
                    "updated_at",
                ]
            )
            create_audit_log(
                actor=request.user if request else None,
                action="medical_report_ocr_completed",
                target=report,
                metadata={
                    "report_id": str(report.id),
                    "patient_id": str(report.patient_id),
                    "consultation_id": (
                        str(report.consultation_id) if report.consultation_id else None
                    ),
                    "source_attachment_id": (
                        str(report.source_attachment_id) if report.source_attachment_id else None
                    ),
                    "processing_status": report.processing_status,
                    "rejection_reason": "",
                    "has_prompt_injection": bool(secure_payload.get("has_prompt_injection", False)),
                    "is_medical_report": True,
                    "raw_text_length": len(report.raw_ocr_text or ""),
                    "cleaned_text_length": len(report.cleaned_report_text or ""),
                },
                request=request,
            )

            if bool(getattr(settings, "CLINICAL_REPORT_LLM_ENABLED", False)) and bool(
                getattr(settings, "CLINICAL_REPORT_LLM_SYNC_AFTER_OCR", False)
            ):
                try:
                    classify_medical_report_with_llm(report=report, request=request)
                except Exception:
                    logger.exception(
                        "Automatic LLM classification failed after OCR completion",
                        extra={"report_id": str(report.id)},
                    )
            return report

        report.cleaned_report_text = ""
        report.is_medical_report = False
        report.report_type = MedicalReportType.NOT_MEDICAL_REPORT
        report.processing_status = MedicalReportProcessingStatus.REJECTED
        report.rejection_reason = secure_payload.get("reason", "not_medical_report")
        report.save(
            update_fields=[
                "raw_ocr_text",
                "cleaned_report_text",
                "is_medical_report",
                "report_type",
                "processing_status",
                "rejection_reason",
                "processing_error",
                "structured_payload",
                "processed_at",
                "updated_at",
            ]
        )
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_ocr_rejected",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
                "source_attachment_id": (
                    str(report.source_attachment_id) if report.source_attachment_id else None
                ),
                "processing_status": report.processing_status,
                "rejection_reason": report.rejection_reason,
                "has_prompt_injection": bool(secure_payload.get("has_prompt_injection", False)),
                "is_medical_report": False,
                "raw_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": 0,
            },
            request=request,
        )
        return report
    except Exception as exc:
        safe_error = _safe_processing_error(exc)
        report.processing_status = MedicalReportProcessingStatus.FAILED
        report.processing_error = safe_error
        report.processed_at = timezone.now()
        report.save(
            update_fields=[
                "processing_status",
                "processing_error",
                "processed_at",
                "updated_at",
            ]
        )
        create_audit_log(
            actor=request.user if request else None,
            action="medical_report_ocr_failed",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
                "source_attachment_id": (
                    str(report.source_attachment_id) if report.source_attachment_id else None
                ),
                "processing_status": report.processing_status,
                "rejection_reason": "",
                "has_prompt_injection": False,
                "is_medical_report": False,
                "raw_text_length": len(report.raw_ocr_text or ""),
                "cleaned_text_length": len(report.cleaned_report_text or ""),
            },
            request=request,
        )
        logger.exception(
            "Medical report OCR processing failed",
            extra={"report_id": str(report.id)},
        )
        if force:
            raise
        return report


def process_medical_report_ocr_by_id(report_id, request=None, force=False):
    report = PatientMedicalReport.objects.select_related(
        "source_attachment",
        "source_message",
        "consultation",
    ).get(id=report_id)
    return process_medical_report_ocr(report=report, request=request, force=force)


def create_patient_medical_report_from_message_attachment(*, attachment, request=None):
    message = attachment.message
    consultation = message.consultation
    patient = consultation.patient

    if message.sender_id != patient.id:
        return None

    if not _is_supported_clinical_attachment(attachment):
        return None

    existing = PatientMedicalReport.objects.filter(source_attachment=attachment).first()
    if existing:
        return existing

    file_obj = getattr(attachment, "file", None)
    file_size = None
    mime_type = ""
    if file_obj is not None:
        try:
            file_size = file_obj.size
        except Exception:
            file_size = None

        raw_file = getattr(file_obj, "file", None)
        if raw_file is not None:
            mime_type = getattr(raw_file, "content_type", "") or ""

    run_ocr_on_upload = bool(getattr(settings, "CLINICAL_REPORT_OCR_ON_UPLOAD", False))
    sync_ocr_on_upload = bool(getattr(settings, "CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD", False))
    initial_status = MedicalReportProcessingStatus.UPLOADED
    if run_ocr_on_upload and not sync_ocr_on_upload:
        initial_status = MedicalReportProcessingStatus.QUEUED

    report = PatientMedicalReport.objects.create(
        patient=patient,
        consultation=consultation,
        source_message=message,
        source_attachment=attachment,
        source=MedicalReportSource.CHAT_ATTACHMENT,
        report_type=MedicalReportType.UNKNOWN,
        processing_status=initial_status,
        title=attachment.original_name or "Uploaded medical report",
        original_filename=attachment.original_name or "",
        mime_type=mime_type,
        file_size=file_size,
        is_medical_report=False,
    )

    create_audit_log(
        actor=message.sender,
        action="clinical_report_created_from_chat_attachment",
        target=report,
        metadata={
            "patient_id": str(patient.id),
            "consultation_id": str(consultation.id),
            "source_message_id": str(message.id),
            "source_attachment_id": str(attachment.id),
            "report_id": str(report.id),
        },
        request=request,
    )

    if run_ocr_on_upload and sync_ocr_on_upload:
        max_inline_mb = int(getattr(settings, "CLINICAL_REPORT_OCR_MAX_INLINE_MB", 5))
        max_inline_bytes = max_inline_mb * 1024 * 1024
        can_run_inline = file_size is None or file_size <= max_inline_bytes
        if can_run_inline:
            try:
                process_medical_report_ocr(report=report, request=request, force=False)
            except Exception:
                logger.exception(
                    "Inline OCR processing failed after report candidate creation",
                    extra={
                        "report_id": str(report.id),
                        "source_attachment_id": str(attachment.id),
                    },
                )
        else:
            report.processing_status = MedicalReportProcessingStatus.QUEUED
            report.save(update_fields=["processing_status", "updated_at"])

    return report


def mark_medical_report_processing_status(report, status, error=""):
    report.processing_status = status
    if error:
        report.processing_error = error
    if status in {
        MedicalReportProcessingStatus.OCR_COMPLETED,
        MedicalReportProcessingStatus.LLM_COMPLETED,
        MedicalReportProcessingStatus.ACCEPTED,
        MedicalReportProcessingStatus.REJECTED,
        MedicalReportProcessingStatus.FAILED,
        MedicalReportProcessingStatus.DOCTOR_REVIEWED,
    }:
        report.processed_at = timezone.now()

    update_fields = ["processing_status", "processing_error", "processed_at", "updated_at"]
    report.save(update_fields=update_fields)
    return report


def link_medical_report_to_record_entry(report, entry):
    report.linked_medical_record_entry = entry
    report.save(update_fields=["linked_medical_record_entry", "updated_at"])
    return report
