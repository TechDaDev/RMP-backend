from django.db import transaction
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    ConsultationStatus,
    DispensingAttemptStatus,
    NotificationType,
    PrescriptionItemStatus,
    PrescriptionStatus,
    UserType,
    VerificationStatus,
)
from apps.notifications.services import create_notification

from .models import DispensingRecord, Prescription, PrescriptionItem


def _is_approved_pharmacist(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.PHARMACIST:
        return False
    try:
        return user.pharmacist_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


def _is_approved_doctor(user) -> bool:
    if not user or not user.is_authenticated or user.user_type != UserType.DOCTOR:
        return False
    try:
        return user.doctor_profile.verification_status == VerificationStatus.APPROVED
    except Exception:
        return False


@transaction.atomic
def create_prescription(consultation, doctor, items_data, request=None):
    valid_statuses = {ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED}
    if consultation.status not in valid_statuses:
        raise ValueError("Prescription can only be created for accepted or doctor_responded consultations.")
    if consultation.assigned_doctor_id != doctor.id:
        raise ValueError("Only the assigned doctor can create a prescription for this consultation.")
    if not _is_approved_doctor(doctor):
        raise ValueError("Doctor must be approved to create prescriptions.")
    if not items_data:
        raise ValueError("At least one prescription item is required.")

    prescription = Prescription(
        consultation=consultation,
        doctor=doctor,
        patient=consultation.patient,
    )
    prescription.full_clean()
    prescription.save()

    for item_data in items_data:
        PrescriptionItem.objects.create(prescription=prescription, **item_data)

    create_audit_log(
        actor=doctor,
        action="prescription_created",
        target=prescription,
        metadata={
            "prescription_id": str(prescription.id),
            "consultation_id": str(consultation.id),
            "patient_id": str(consultation.patient_id),
            "doctor_id": str(doctor.id),
            "status": prescription.status,
        },
        request=request,
    )
    create_notification(
        recipient=consultation.patient,
        notification_type=NotificationType.PRESCRIPTION,
        title="Prescription issued",
        message="Your doctor has issued a prescription for your consultation.",
        data={"prescription_id": str(prescription.id), "consultation_id": str(consultation.id), "status": prescription.status},
    )
    
    # Broadcast realtime prescription event (Phase 14)
    def broadcast_update():
        from apps.realtime.services import broadcast_prescription_updated
        try:
            broadcast_prescription_updated(prescription)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast prescription.updated event: {e}")
    
    transaction.on_commit(broadcast_update)
    
    return prescription


def get_prescription_by_qr_token(token, pharmacist):
    if not _is_approved_pharmacist(pharmacist):
        raise PermissionError("Only approved pharmacists can scan QR tokens.")

    try:
        prescription = Prescription.objects.select_related("doctor", "patient", "consultation").get(qr_token=token)
    except Prescription.DoesNotExist:
        raise ValueError("Invalid QR token.")

    if prescription.is_expired() and prescription.status not in (
        PrescriptionStatus.CANCELLED,
        PrescriptionStatus.FULLY_DISPENSED,
    ):
        prescription.status = PrescriptionStatus.EXPIRED
        prescription.save(update_fields=["status", "updated_at"])

    return prescription


def get_remaining_items_for_pharmacist(prescription):
    return prescription.items.filter(status=PrescriptionItemStatus.PENDING)


@transaction.atomic
def dispense_prescription_items(prescription, pharmacist, items_payload, request=None):
    if not _is_approved_pharmacist(pharmacist):
        raise PermissionError("Only approved pharmacists can dispense items.")

    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)

    if prescription.is_expired() and prescription.status not in (
        PrescriptionStatus.CANCELLED,
        PrescriptionStatus.FULLY_DISPENSED,
    ):
        prescription.status = PrescriptionStatus.EXPIRED
        prescription.save(update_fields=["status", "updated_at"])

    if prescription.is_locked():
        raise ValueError("This prescription is locked and cannot be dispensed.")

    records = []
    for entry in items_payload:
        item_id = entry["prescription_item_id"]
        attempt_status = entry["status"]

        item = (
            PrescriptionItem.objects.select_for_update()
            .filter(pk=item_id, prescription=prescription)
            .first()
        )
        if item is None:
            raise ValueError(f"Prescription item {item_id} not found in this prescription.")

        if attempt_status == DispensingAttemptStatus.DISPENSED:
            if item.status != PrescriptionItemStatus.PENDING:
                raise ValueError(f"Item {item_id} is not pending and cannot be dispensed.")
            item.status = PrescriptionItemStatus.DISPENSED
            item.dispensed_at = timezone.now()
            item.save(update_fields=["status", "dispensed_at", "updated_at"])

        record = DispensingRecord.objects.create(
            prescription=prescription,
            prescription_item=item,
            pharmacist=pharmacist,
            status=attempt_status,
            dispensed_quantity=entry.get("dispensed_quantity", ""),
            note=entry.get("note", ""),
        )
        records.append(record)

        audit_action = (
            "prescription_item_dispensed"
            if attempt_status == DispensingAttemptStatus.DISPENSED
            else "prescription_item_unavailable"
        )
        create_audit_log(
            actor=pharmacist,
            action=audit_action,
            target=record,
            metadata={
                "prescription_id": str(prescription.id),
                "consultation_id": str(prescription.consultation_id),
                "patient_id": str(prescription.patient_id),
                "doctor_id": str(prescription.doctor_id),
                "pharmacist_id": str(pharmacist.id),
                "item_id": str(item.id),
                "status": attempt_status,
            },
            request=request,
        )
        if attempt_status == DispensingAttemptStatus.DISPENSED:
            create_notification(
                recipient=prescription.doctor,
                notification_type=NotificationType.DISPENSING,
                title="Medication item dispensed",
                message="A medication item in your prescription has been dispensed.",
                data={"prescription_id": str(prescription.id), "item_id": str(item.id)},
            )
        elif attempt_status == DispensingAttemptStatus.UNAVAILABLE:
            create_notification(
                recipient=prescription.doctor,
                notification_type=NotificationType.DISPENSING,
                title="Medication unavailable",
                message="A medication item in your prescription is unavailable.",
                data={"prescription_id": str(prescription.id), "item_id": str(item.id)},
            )

    # Refresh prescription and update status
    prescription.refresh_from_db()
    prescription.update_status_from_items()

    if prescription.status == PrescriptionStatus.FULLY_DISPENSED:
        create_audit_log(
            actor=pharmacist,
            action="prescription_fully_dispensed",
            target=prescription,
            metadata={
                "prescription_id": str(prescription.id),
                "consultation_id": str(prescription.consultation_id),
                "patient_id": str(prescription.patient_id),
                "doctor_id": str(prescription.doctor_id),
                "pharmacist_id": str(pharmacist.id),
                "status": prescription.status,
            },
            request=request,
        )
        create_notification(
            recipient=prescription.patient,
            notification_type=NotificationType.DISPENSING,
            title="Prescription fully dispensed",
            message="All items in your prescription have been processed.",
            data={"prescription_id": str(prescription.id), "status": prescription.status},
        )
    
    # Broadcast realtime prescription update event (Phase 14)
    def broadcast_update():
        from apps.realtime.services import broadcast_prescription_updated
        try:
            broadcast_prescription_updated(prescription)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast prescription.updated event: {e}")
    
    transaction.on_commit(broadcast_update)

    return prescription
