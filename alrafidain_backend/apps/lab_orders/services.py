import secrets
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import (
    BloodGroup,
    ConsultationStatus,
    LabCompletionAttemptStatus,
    LabOrderItemStatus,
    LabOrderStatus,
    LabResultStatus,
    LabResultValueType,
    MedicalRecordCategory,
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    NotificationType,
)
from apps.notifications.services import create_notification
from apps.patient_records.services import get_or_create_patient_medical_record

from .models import LabCompletionRecord, LabOrder, LabOrderItem, LabResult, LabResultCorrection
from .permissions import is_approved_doctor, is_approved_laboratorian


def generate_qr_token():
    for _ in range(10):
        token = secrets.token_urlsafe(32)
        if not LabOrder.objects.filter(qr_token=token).exists():
            return token
    raise RuntimeError("Could not generate a unique QR token.")


@transaction.atomic
def create_lab_order(consultation, doctor, items_data, request=None):
    valid_statuses = {ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED}
    if consultation.status not in valid_statuses:
        raise ValueError(
            "Lab order can only be created for accepted or doctor_responded consultations."
        )
    if consultation.assigned_doctor_id != doctor.id:
        raise ValueError("Only assigned doctor can create a lab order for this consultation.")
    if not is_approved_doctor(doctor):
        raise ValueError("Doctor must be approved to create lab orders.")
    if not items_data:
        raise ValueError("At least one lab order item is required.")

    lab_order = LabOrder(
        consultation=consultation,
        doctor=doctor,
        patient=consultation.patient,
    )
    lab_order.full_clean()
    lab_order.save()

    for item_data in items_data:
        LabOrderItem.objects.create(lab_order=lab_order, **item_data)

    create_audit_log(
        actor=doctor,
        action="lab_order_created",
        target=lab_order,
        metadata={
            "lab_order_id": str(lab_order.id),
            "consultation_id": str(consultation.id),
            "patient_id": str(consultation.patient_id),
            "doctor_id": str(doctor.id),
            "status": lab_order.status,
        },
        request=request,
    )

    create_notification(
        recipient=consultation.patient,
        notification_type=NotificationType.LAB_ORDER,
        title="Lab order issued",
        message="A lab order QR code has been issued for you.",
        data={
            "lab_order_id": str(lab_order.id),
            "consultation_id": str(consultation.id),
            "status": lab_order.status,
        },
    )

    # Broadcast realtime lab order event (Phase 14)
    def broadcast_update():
        from apps.realtime.services import broadcast_lab_order_updated

        try:
            broadcast_lab_order_updated(lab_order)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast lab_order.updated event: {e}")

    transaction.on_commit(broadcast_update, robust=True)

    return lab_order


def get_lab_order_by_qr_token(token, laboratorian, request=None):
    if not is_approved_laboratorian(laboratorian):
        raise PermissionError("Only approved laboratorians can scan QR tokens.")

    try:
        lab_order = LabOrder.objects.select_related("doctor", "patient", "consultation").get(
            qr_token=token
        )
    except LabOrder.DoesNotExist:
        raise ValueError("Invalid QR token.") from None

    if lab_order.is_expired() and lab_order.status not in (
        LabOrderStatus.CANCELLED,
        LabOrderStatus.FULLY_COMPLETED,
    ):
        lab_order.status = LabOrderStatus.EXPIRED
        lab_order.save(update_fields=["status", "updated_at"])

    create_audit_log(
        actor=laboratorian,
        action="lab_order_qr_scanned",
        target=lab_order,
        metadata={
            "lab_order_id": str(lab_order.id),
            "consultation_id": str(lab_order.consultation_id),
            "patient_id": str(lab_order.patient_id),
            "doctor_id": str(lab_order.doctor_id),
            "laboratorian_id": str(laboratorian.id),
            "status": lab_order.status,
        },
        request=request,
    )

    return lab_order


def get_remaining_tests_for_laboratorian(lab_order):
    return lab_order.items.filter(status=LabOrderItemStatus.PENDING)


def get_completed_tests_for_laboratorian(lab_order):
    """
    Get all completed and cancelled items for a lab order.
    Safe to return: laboratorian can see item status and result metadata.
    Does NOT expose result values, doctor_notes, or patient-hidden fields.
    """
    return lab_order.items.filter(
        status__in=[LabOrderItemStatus.COMPLETED, LabOrderItemStatus.CANCELLED]
    ).select_related("result")


@transaction.atomic
def cancel_lab_order(*, lab_order, doctor, request=None):
    lab_order = LabOrder.objects.select_for_update().get(pk=lab_order.pk)

    if lab_order.doctor_id != doctor.id:
        raise PermissionError("You are not the ordering doctor for this lab order.")

    if lab_order.items.filter(status=LabOrderItemStatus.COMPLETED).exists():
        raise ValueError("Cannot cancel lab order after any item has been completed.")

    if lab_order.status == LabOrderStatus.CANCELLED:
        raise ValueError("Lab order is already cancelled.")

    now = timezone.now()
    lab_order.status = LabOrderStatus.CANCELLED
    lab_order.cancelled_at = now
    lab_order.save(update_fields=["status", "cancelled_at", "updated_at"])

    lab_order.items.filter(status=LabOrderItemStatus.PENDING).update(
        status=LabOrderItemStatus.CANCELLED,
        cancelled_at=now,
    )

    create_audit_log(
        actor=doctor,
        action="lab_order_cancelled",
        target=lab_order,
        metadata={
            "lab_order_id": str(lab_order.id),
            "consultation_id": str(lab_order.consultation_id),
            "patient_id": str(lab_order.patient_id),
            "doctor_id": str(doctor.id),
            "status": lab_order.status,
        },
        request=request,
    )

    return lab_order


@transaction.atomic
def complete_lab_order_items(lab_order, laboratorian, items_payload, request=None):
    if not is_approved_laboratorian(laboratorian):
        raise PermissionError("Only approved laboratorians can complete tests.")

    lab_order = LabOrder.objects.select_for_update().get(pk=lab_order.pk)

    if lab_order.is_expired() and lab_order.status not in (
        LabOrderStatus.CANCELLED,
        LabOrderStatus.FULLY_COMPLETED,
    ):
        lab_order.status = LabOrderStatus.EXPIRED
        lab_order.save(update_fields=["status", "updated_at"])

    if lab_order.is_locked():
        raise ValueError("This lab order is locked and cannot be updated.")

    for entry in items_payload:
        item_id = entry["lab_order_item_id"]
        attempt_status = entry["status"]

        item = (
            LabOrderItem.objects.select_for_update().filter(pk=item_id, lab_order=lab_order).first()
        )
        if item is None:
            raise ValueError(f"Lab order item {item_id} not found in this lab order.")

        if attempt_status == LabCompletionAttemptStatus.COMPLETED:
            if item.status != LabOrderItemStatus.PENDING:
                raise ValueError(f"Item {item_id} is not pending and cannot be completed.")
            item.status = LabOrderItemStatus.COMPLETED
            item.completed_at = timezone.now()
            item.save(update_fields=["status", "completed_at", "updated_at"])

        record = LabCompletionRecord.objects.create(
            lab_order=lab_order,
            lab_order_item=item,
            laboratorian=laboratorian,
            status=attempt_status,
            note=entry.get("note", ""),
        )

        audit_action = (
            "lab_order_item_completed"
            if attempt_status == LabCompletionAttemptStatus.COMPLETED
            else "lab_order_item_unavailable"
        )
        create_audit_log(
            actor=laboratorian,
            action=audit_action,
            target=record,
            metadata={
                "lab_order_id": str(lab_order.id),
                "consultation_id": str(lab_order.consultation_id),
                "patient_id": str(lab_order.patient_id),
                "doctor_id": str(lab_order.doctor_id),
                "laboratorian_id": str(laboratorian.id),
                "item_id": str(item.id),
                "status": attempt_status,
            },
            request=request,
        )

        if attempt_status == LabCompletionAttemptStatus.COMPLETED:
            create_notification(
                recipient=lab_order.doctor,
                notification_type=NotificationType.LAB_ORDER,
                title="Lab test completed",
                message="A requested lab test was marked as completed.",
                data={"lab_order_id": str(lab_order.id), "lab_order_item_id": str(item.id)},
            )
        elif attempt_status == LabCompletionAttemptStatus.UNAVAILABLE:
            create_notification(
                recipient=lab_order.doctor,
                notification_type=NotificationType.LAB_ORDER,
                title="Lab test unavailable",
                message="A laboratorian marked one requested test as unavailable.",
                data={"lab_order_id": str(lab_order.id), "lab_order_item_id": str(item.id)},
            )

    lab_order.refresh_from_db()
    previous_status = lab_order.status
    lab_order.update_status_from_items()

    if (
        lab_order.status == LabOrderStatus.FULLY_COMPLETED
        and previous_status != LabOrderStatus.FULLY_COMPLETED
    ):
        create_audit_log(
            actor=laboratorian,
            action="lab_order_fully_completed",
            target=lab_order,
            metadata={
                "lab_order_id": str(lab_order.id),
                "consultation_id": str(lab_order.consultation_id),
                "patient_id": str(lab_order.patient_id),
                "doctor_id": str(lab_order.doctor_id),
                "laboratorian_id": str(laboratorian.id),
                "status": lab_order.status,
            },
            request=request,
        )
        create_notification(
            recipient=lab_order.patient,
            notification_type=NotificationType.LAB_ORDER,
            title="Lab order fully completed",
            message="Your lab order has been completed.",
            data={"lab_order_id": str(lab_order.id), "status": lab_order.status},
        )

    # Broadcast realtime lab order update event (Phase 14)
    def broadcast_update():
        from apps.realtime.services import broadcast_lab_order_updated

        try:
            broadcast_lab_order_updated(lab_order)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast lab_order.updated event: {e}")

    transaction.on_commit(broadcast_update, robust=True)

    return lab_order


def _result_payload_snapshot(lab_result):
    return {
        "status": lab_result.status,
        "value_type": lab_result.value_type,
        "text_value": lab_result.text_value,
        "numeric_value": str(lab_result.numeric_value)
        if lab_result.numeric_value is not None
        else None,
        "blood_group_value": lab_result.blood_group_value,
        "unit": lab_result.unit,
        "reference_range": lab_result.reference_range,
        "flag": lab_result.flag,
        "laboratorian_notes": lab_result.laboratorian_notes,
    }


def _json_safe_dict(data: dict) -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, (Decimal, UUID)):
            out[key] = str(value)
        else:
            out[key] = value
    return out


@transaction.atomic
def create_lab_result(lab_order_item, laboratorian, result_data, request=None):
    if not is_approved_laboratorian(laboratorian):
        raise PermissionError("Only approved laboratorians can create lab results.")
    if lab_order_item.status != LabOrderItemStatus.COMPLETED:
        raise ValueError("Lab result can only be created for completed items.")
    if LabResult.objects.filter(lab_order_item=lab_order_item).exists():
        raise ValueError("A result already exists for this lab order item.")

    has_completed_attempt = LabCompletionRecord.objects.filter(
        lab_order_item=lab_order_item,
        laboratorian=laboratorian,
        status=LabCompletionAttemptStatus.COMPLETED,
    ).exists()
    if not has_completed_attempt:
        raise PermissionError("You can only submit results for items you completed.")

    lab_order = lab_order_item.lab_order
    lab_result = LabResult.objects.create(
        lab_order=lab_order,
        lab_order_item=lab_order_item,
        patient=lab_order.patient,
        doctor=lab_order.doctor,
        laboratorian=laboratorian,
        status=LabResultStatus.SUBMITTED,
        submitted_at=timezone.now(),
        **result_data,
    )
    lab_result.full_clean()
    lab_result.save()

    create_audit_log(
        actor=laboratorian,
        action="lab_result_created",
        target=lab_result,
        metadata={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_order.id),
            "lab_order_item_id": str(lab_order_item.id),
            "patient_id": str(lab_order.patient_id),
            "doctor_id": str(lab_order.doctor_id),
            "laboratorian_id": str(laboratorian.id),
            "status": lab_result.status,
            "value_type": lab_result.value_type,
        },
        request=request,
    )

    create_notification(
        recipient=lab_order.doctor,
        notification_type=NotificationType.LAB_ORDER,
        title="Lab result submitted",
        message="A lab result has been submitted for your review.",
        data={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_order.id),
            "lab_order_item_id": str(lab_order_item.id),
        },
    )

    return lab_result


@transaction.atomic
def correct_lab_result(lab_result, corrected_by, new_data, reason, request=None):
    if not reason or not reason.strip():
        raise ValueError("Correction reason is required.")
    if corrected_by.id != lab_result.laboratorian_id:
        raise PermissionError("Only the original laboratorian can correct this result in MVP.")
    if lab_result.status not in {LabResultStatus.SUBMITTED, LabResultStatus.CORRECTED}:
        raise ValueError("Result can only be corrected while submitted or corrected.")

    previous_data = _result_payload_snapshot(lab_result)

    for field in [
        "value_type",
        "text_value",
        "numeric_value",
        "blood_group_value",
        "unit",
        "reference_range",
        "flag",
        "laboratorian_notes",
    ]:
        if field in new_data:
            setattr(lab_result, field, new_data[field])

    lab_result.status = LabResultStatus.CORRECTED
    lab_result.corrected_at = timezone.now()
    lab_result.full_clean()
    lab_result.save()

    LabResultCorrection.objects.create(
        lab_result=lab_result,
        corrected_by=corrected_by,
        previous_data=previous_data,
        new_data=_json_safe_dict(
            {k: v for k, v in new_data.items() if k in previous_data or k == "value_type"}
        ),
        reason=reason,
    )

    create_audit_log(
        actor=corrected_by,
        action="lab_result_corrected",
        target=lab_result,
        metadata={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
            "patient_id": str(lab_result.patient_id),
            "doctor_id": str(lab_result.doctor_id),
            "laboratorian_id": str(corrected_by.id),
            "status": lab_result.status,
            "value_type": lab_result.value_type,
        },
        request=request,
    )

    create_notification(
        recipient=lab_result.doctor,
        notification_type=NotificationType.LAB_ORDER,
        title="Lab result corrected",
        message="A submitted lab result has been corrected.",
        data={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
        },
    )

    return lab_result


@transaction.atomic
def review_lab_result(
    lab_result, doctor, doctor_notes=None, release_to_patient=False, request=None
):
    if doctor.id != lab_result.doctor_id:
        raise PermissionError("Only ordering doctor can review this result.")

    lab_result.status = LabResultStatus.REVIEWED
    lab_result.reviewed_at = timezone.now()
    if doctor_notes is not None:
        lab_result.doctor_notes = doctor_notes

    if release_to_patient:
        lab_result.status = LabResultStatus.RELEASED
        lab_result.released_at = timezone.now()

    lab_result.save(
        update_fields=["status", "reviewed_at", "doctor_notes", "released_at", "updated_at"]
    )

    create_audit_log(
        actor=doctor,
        action="lab_result_reviewed",
        target=lab_result,
        metadata={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
            "patient_id": str(lab_result.patient_id),
            "doctor_id": str(doctor.id),
            "laboratorian_id": str(lab_result.laboratorian_id),
            "status": lab_result.status,
            "value_type": lab_result.value_type,
        },
        request=request,
    )

    if release_to_patient:
        create_notification(
            recipient=lab_result.patient,
            notification_type=NotificationType.LAB_ORDER,
            title="Lab result released",
            message="A lab result has been released for you.",
            data={
                "lab_result_id": str(lab_result.id),
                "lab_order_id": str(lab_result.lab_order_id),
                "lab_order_item_id": str(lab_result.lab_order_item_id),
            },
        )

    return lab_result


@transaction.atomic
def release_lab_result_to_patient(lab_result, doctor, request=None):
    if doctor.id != lab_result.doctor_id:
        raise PermissionError("Only ordering doctor can release this result.")

    lab_result.status = LabResultStatus.RELEASED
    if not lab_result.reviewed_at:
        lab_result.reviewed_at = timezone.now()
    lab_result.released_at = timezone.now()
    lab_result.save(update_fields=["status", "reviewed_at", "released_at", "updated_at"])

    create_audit_log(
        actor=doctor,
        action="lab_result_released",
        target=lab_result,
        metadata={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
            "patient_id": str(lab_result.patient_id),
            "doctor_id": str(doctor.id),
            "laboratorian_id": str(lab_result.laboratorian_id),
            "status": lab_result.status,
            "value_type": lab_result.value_type,
        },
        request=request,
    )

    create_notification(
        recipient=lab_result.patient,
        notification_type=NotificationType.LAB_ORDER,
        title="Lab result released",
        message="A lab result has been released for you.",
        data={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
        },
    )

    # Broadcast realtime lab result release event (Phase 14)
    def broadcast_release():
        from apps.realtime.services import broadcast_lab_result_released

        try:
            broadcast_lab_result_released(lab_result)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast lab_result.released event: {e}")

    transaction.on_commit(broadcast_release, robust=True)

    return lab_result


@transaction.atomic
def link_lab_result_to_medical_record(lab_result, doctor, request=None):
    if doctor.id != lab_result.doctor_id:
        raise PermissionError("Only ordering doctor can link this result.")
    if lab_result.status not in {LabResultStatus.REVIEWED, LabResultStatus.RELEASED}:
        raise ValueError("Lab result must be reviewed or released before linking.")
    if lab_result.is_linked_to_medical_record:
        raise ValueError("Lab result is already linked to medical record.")

    record = get_or_create_patient_medical_record(lab_result.patient)
    now = timezone.now()

    if lab_result.value_type == LabResultValueType.BLOOD_GROUP:
        if not lab_result.blood_group_value or lab_result.blood_group_value == BloodGroup.UNKNOWN:
            raise ValueError("Blood group result requires a valid blood_group_value to link.")
        blood_group_record = record.blood_group_record
        blood_group_record.blood_group = lab_result.blood_group_value
        blood_group_record.verification_status = (
            MedicalRecordVerificationStatus.LABORATORY_CONFIRMED
        )
        blood_group_record.source_user = lab_result.laboratorian
        blood_group_record.verified_by = lab_result.laboratorian
        blood_group_record.verified_at = now
        blood_group_record.notes = f"Linked from lab result {lab_result.id}."
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
        lab_result.linked_blood_group_record = blood_group_record
    else:
        if lab_result.value_type == LabResultValueType.NUMERIC:
            result_value = f"{lab_result.numeric_value} {lab_result.unit}".strip()
        elif lab_result.value_type == LabResultValueType.BLOOD_GROUP:
            result_value = lab_result.blood_group_value
        else:
            result_value = lab_result.text_value or "Result file attached"

        linked_entry = record.entries.create(
            category=MedicalRecordCategory.GENERAL_NOTE,
            title=lab_result.lab_order_item.test_name,
            value=result_value,
            verification_status=MedicalRecordVerificationStatus.LABORATORY_CONFIRMED,
            source_user=lab_result.laboratorian,
            source_role=MedicalRecordSourceRole.LABORATORIAN,
            verified_by=lab_result.laboratorian,
            verified_at=now,
            notes=f"Linked from lab result {lab_result.id}",
        )
        lab_result.linked_entry = linked_entry

    lab_result.is_linked_to_medical_record = True
    lab_result.save(
        update_fields=[
            "is_linked_to_medical_record",
            "linked_entry",
            "linked_blood_group_record",
            "updated_at",
        ]
    )

    create_audit_log(
        actor=doctor,
        action="lab_result_linked_to_medical_record",
        target=lab_result,
        metadata={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
            "patient_id": str(lab_result.patient_id),
            "doctor_id": str(doctor.id),
            "laboratorian_id": str(lab_result.laboratorian_id),
            "status": lab_result.status,
            "value_type": lab_result.value_type,
        },
        request=request,
    )

    create_notification(
        recipient=lab_result.patient,
        notification_type=NotificationType.MEDICAL_RECORD,
        title="Medical record updated",
        message="A lab-confirmed result has been linked to your medical record.",
        data={
            "lab_result_id": str(lab_result.id),
            "lab_order_id": str(lab_result.lab_order_id),
            "lab_order_item_id": str(lab_result.lab_order_item_id),
        },
    )

    return lab_result
