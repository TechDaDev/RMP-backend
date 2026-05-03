from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    ConsultationStatus,
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    NotificationType,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.notifications.services import create_notification

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord

User = get_user_model()


ALLOWED_DOCTOR_RECORD_STATUSES = [
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.DOCTOR_RESPONDED,
    ConsultationStatus.CLOSED,
]


def _is_approved_doctor(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.DOCTOR:
        return False
    try:
        return user.doctor_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


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
    if not _is_approved_doctor(doctor):
        return False
    if not patient or patient.user_type != UserType.PATIENT:
        return False

    return Consultation.objects.filter(
        patient=patient,
        assigned_doctor=doctor,
        status__in=ALLOWED_DOCTOR_RECORD_STATUSES,
    ).exists()


def create_medical_record_entry(record, source_user, category, title, value, notes=None, request=None):
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
        raise PermissionError("Only patient or approved doctor can create generic medical record entries.")

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
    entry.save(update_fields=["verification_status", "verified_by", "verified_at", "notes", "updated_at"])

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
