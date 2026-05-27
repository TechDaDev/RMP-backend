from __future__ import annotations

from dataclasses import dataclass

from apps.common.choices import ConsultationStatus
from apps.common.policies import RoleAccessPolicy
from apps.consultations.models import Consultation
from apps.lab_requests.models import LabOrderRequest
from apps.pharmacy_requests.models import PharmacyPrescriptionRequest

from .models import PaymentIntent


@dataclass(frozen=True)
class PaymentTarget:
    service_type: str
    reference_id: object
    amount: object
    currency: str
    provider_user: object
    provider_type: str
    description: str
    amount_source: str


def has_succeeded_payment(service_type: str, reference_id) -> bool:
    if not reference_id:
        return False
    return PaymentIntent.objects.filter(
        service_type=service_type,
        reference_id=reference_id,
        status=PaymentIntent.Status.SUCCEEDED,
    ).exists()


def resolve_payment_target(service_type: str, reference_id, user) -> PaymentTarget:
    if service_type == PaymentIntent.ServiceType.LAB_REQUEST:
        return _resolve_lab_request(reference_id=reference_id, user=user)
    if service_type == PaymentIntent.ServiceType.PHARMACY_REQUEST:
        return _resolve_pharmacy_request(reference_id=reference_id, user=user)
    if service_type == PaymentIntent.ServiceType.CONSULTATION:
        return _resolve_consultation(reference_id=reference_id, user=user)

    raise ValueError("Service payment resolution is not supported for this service type.")


def _resolve_lab_request(*, reference_id, user) -> PaymentTarget:
    try:
        request_obj = LabOrderRequest.objects.select_related("patient", "lab", "lab__user").get(id=reference_id)
    except LabOrderRequest.DoesNotExist as exc:
        raise ValueError("Lab request was not found.") from exc

    if not (RoleAccessPolicy.is_admin_or_staff(user) or request_obj.patient_id == user.id):
        raise ValueError("You do not have permission to pay this lab request.")

    if request_obj.payment_status == request_obj.PaymentStatus.PAID:
        raise ValueError("Service object is already paid.")

    if request_obj.status != LabOrderRequest.Status.ACCEPTED:
        raise ValueError("Lab request must be accepted before payment.")

    if request_obj.total_price <= 0:
        raise ValueError("Lab request total price must be positive before payment.")

    provider_user = getattr(request_obj.lab, "user", None)
    if not provider_user:
        raise ValueError("Lab request provider user is not configured.")

    return PaymentTarget(
        service_type=PaymentIntent.ServiceType.LAB_REQUEST,
        reference_id=request_obj.id,
        amount=request_obj.total_price,
        currency=request_obj.currency,
        provider_user=provider_user,
        provider_type="lab",
        description=f"Payment for lab request {request_obj.id}",
        amount_source="lab_request.total_price",
    )


def _resolve_pharmacy_request(*, reference_id, user) -> PaymentTarget:
    try:
        request_obj = PharmacyPrescriptionRequest.objects.select_related(
            "patient", "pharmacy", "pharmacy__user"
        ).get(id=reference_id)
    except PharmacyPrescriptionRequest.DoesNotExist as exc:
        raise ValueError("Pharmacy request was not found.") from exc

    if not (RoleAccessPolicy.is_admin_or_staff(user) or request_obj.patient_id == user.id):
        raise ValueError("You do not have permission to pay this pharmacy request.")

    if request_obj.payment_status == request_obj.PaymentStatus.PAID:
        raise ValueError("Service object is already paid.")

    if request_obj.status != PharmacyPrescriptionRequest.Status.ACCEPTED:
        raise ValueError("Pharmacy request must be accepted before payment.")

    if request_obj.total_price <= 0:
        raise ValueError("Pharmacy request total price must be positive before payment.")

    provider_user = getattr(request_obj.pharmacy, "user", None)
    if not provider_user:
        raise ValueError("Pharmacy request provider user is not configured.")

    return PaymentTarget(
        service_type=PaymentIntent.ServiceType.PHARMACY_REQUEST,
        reference_id=request_obj.id,
        amount=request_obj.total_price,
        currency=request_obj.currency,
        provider_user=provider_user,
        provider_type="pharmacy",
        description=f"Payment for pharmacy request {request_obj.id}",
        amount_source="pharmacy_request.total_price",
    )


def _resolve_consultation(*, reference_id, user) -> PaymentTarget:
    try:
        consultation = Consultation.objects.select_related("patient", "assigned_doctor").get(id=reference_id)
    except Consultation.DoesNotExist as exc:
        raise ValueError("Consultation was not found.") from exc

    if not (RoleAccessPolicy.is_admin_or_staff(user) or consultation.patient_id == user.id):
        raise ValueError("You do not have permission to pay this consultation.")

    if consultation.payment_status == consultation.PaymentStatus.PAID:
        raise ValueError("Service object is already paid.")

    if consultation.status != ConsultationStatus.ACCEPTED:
        raise ValueError("Consultation must be accepted before payment.")

    if consultation.consultation_fee is None or consultation.consultation_fee <= 0:
        raise ValueError("Consultation fee is not configured for this consultation.")

    provider_user = consultation.assigned_doctor
    if not provider_user:
        raise ValueError("Consultation doctor is not configured for payment.")

    return PaymentTarget(
        service_type=PaymentIntent.ServiceType.CONSULTATION,
        reference_id=consultation.id,
        amount=consultation.consultation_fee,
        currency=consultation.consultation_currency or "IQD",
        provider_user=provider_user,
        provider_type="doctor",
        description=f"Payment for consultation {consultation.id}",
        amount_source="consultation.consultation_fee",
    )
