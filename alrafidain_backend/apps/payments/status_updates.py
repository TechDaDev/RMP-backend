from __future__ import annotations

from django.utils import timezone

from .models import PaymentIntent


def get_service_object_for_intent(payment_intent: PaymentIntent):
    if not payment_intent.reference_id:
        return None

    if payment_intent.service_type == PaymentIntent.ServiceType.CONSULTATION:
        from apps.consultations.models import Consultation

        return Consultation.objects.filter(id=payment_intent.reference_id).first()
    if payment_intent.service_type == PaymentIntent.ServiceType.LAB_REQUEST:
        from apps.lab_requests.models import LabOrderRequest

        return LabOrderRequest.objects.filter(id=payment_intent.reference_id).first()
    if payment_intent.service_type == PaymentIntent.ServiceType.PHARMACY_REQUEST:
        from apps.pharmacy_requests.models import PharmacyPrescriptionRequest

        return PharmacyPrescriptionRequest.objects.filter(id=payment_intent.reference_id).first()

    return None


def mark_service_payment_pending(payment_intent: PaymentIntent) -> None:
    service_obj = get_service_object_for_intent(payment_intent)
    if not service_obj:
        return

    if service_obj.payment_status == service_obj.PaymentStatus.PAID:
        return

    if service_obj.payment_status in {
        service_obj.PaymentStatus.UNPAID,
        service_obj.PaymentStatus.FAILED,
    }:
        service_obj.payment_status = service_obj.PaymentStatus.PAYMENT_PENDING
        service_obj.payment_intent = payment_intent
        service_obj.save(update_fields=["payment_status", "payment_intent", "updated_at"])


def mark_service_paid(payment_intent: PaymentIntent) -> None:
    service_obj = get_service_object_for_intent(payment_intent)
    if not service_obj:
        return

    service_obj.payment_status = service_obj.PaymentStatus.PAID
    service_obj.payment_intent = payment_intent
    service_obj.paid_at = timezone.now()
    service_obj.save(update_fields=["payment_status", "payment_intent", "paid_at", "updated_at"])


def mark_service_payment_failed(payment_intent: PaymentIntent) -> None:
    service_obj = get_service_object_for_intent(payment_intent)
    if not service_obj:
        return

    service_obj.payment_status = service_obj.PaymentStatus.FAILED
    service_obj.payment_intent = payment_intent
    service_obj.payment_failed_at = timezone.now()
    service_obj.save(
        update_fields=["payment_status", "payment_intent", "payment_failed_at", "updated_at"]
    )
