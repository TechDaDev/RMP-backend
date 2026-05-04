"""Tests for realtime permissions and broadcast services."""

from types import SimpleNamespace
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    MessageSenderRole,
    MessageType,
    MedicalSpecialty,
    NotificationType,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile

from .permissions import can_connect_consultation_messages, can_connect_user_socket
from .services import (
    broadcast_consultation_updated,
    broadcast_lab_order_updated,
    broadcast_lab_result_released,
    broadcast_message_created,
    broadcast_messages_marked_read,
    broadcast_notification_created,
    broadcast_prescription_updated,
    broadcast_unread_notification_count,
)

User = get_user_model()


def create_patient(email="patient@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Pat",
        last_name="Ient",
        user_type=UserType.PATIENT,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def create_doctor(email="doctor@example.com"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Doc",
        last_name="Tor",
        user_type=UserType.DOCTOR,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.CARDIOLOGY,
        verification_status=VerificationStatus.APPROVED,
    )
    return user


def create_consultation(patient, doctor, status=ConsultationStatus.ACCEPTED):
    return Consultation.objects.create(
        id=uuid4(),
        patient=patient,
        assigned_doctor=doctor,
        status=status,
        duration=ConsultationDuration.ONE_TO_THREE_DAYS,
        severity=SeverityLevel.MODERATE,
    )


class PermissionTests(TransactionTestCase):
    def test_can_connect_user_socket_authenticated(self):
        self.assertTrue(can_connect_user_socket(create_patient()))

    def test_can_connect_user_socket_anonymous(self):
        self.assertFalse(can_connect_user_socket(AnonymousUser()))

    def test_consultation_messages_patient_allowed(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        allowed = async_to_sync(can_connect_consultation_messages)(patient, consultation)
        self.assertTrue(allowed)

    def test_consultation_messages_assigned_doctor_allowed(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        allowed = async_to_sync(can_connect_consultation_messages)(doctor, consultation)
        self.assertTrue(allowed)

    def test_consultation_messages_other_patient_denied(self):
        patient = create_patient("p1@example.com")
        other_patient = create_patient("p2@example.com")
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        allowed = async_to_sync(can_connect_consultation_messages)(other_patient, consultation)
        self.assertFalse(allowed)

    def test_consultation_messages_unassigned_doctor_denied(self):
        patient = create_patient()
        doctor = create_doctor("d1@example.com")
        other_doctor = create_doctor("d2@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        allowed = async_to_sync(can_connect_consultation_messages)(other_doctor, consultation)
        self.assertFalse(allowed)

    def test_consultation_messages_denied_for_submitted(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.SUBMITTED)
        allowed = async_to_sync(can_connect_consultation_messages)(patient, consultation)
        self.assertFalse(allowed)

    def test_consultation_messages_allowed_for_closed(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.CLOSED)
        allowed = async_to_sync(can_connect_consultation_messages)(patient, consultation)
        self.assertTrue(allowed)


class BroadcastServiceTests(TransactionTestCase):
    def test_broadcast_notification_created(self):
        patient = create_patient()
        notification = Notification.objects.create(
            recipient=patient,
            notification_type=NotificationType.PRESCRIPTION,
            title="Test",
            message="Test",
        )
        broadcast_notification_created(notification)

    def test_broadcast_unread_notification_count(self):
        patient = create_patient()
        broadcast_unread_notification_count(patient)

    def test_broadcast_message_created(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        message = ConsultationMessage.objects.create(
            consultation=consultation,
            sender=patient,
            sender_role=MessageSenderRole.PATIENT,
            message_type=MessageType.TEXT,
            body="Test message",
        )
        broadcast_message_created(message)

    def test_broadcast_messages_marked_read(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        broadcast_messages_marked_read(consultation, patient, 3)

    def test_broadcast_consultation_updated(self):
        patient = create_patient()
        doctor = create_doctor()
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        broadcast_consultation_updated(consultation)

    def test_broadcast_prescription_updated(self):
        prescription = SimpleNamespace(
            id=uuid4(),
            status="issued",
            expires_at=None,
            fully_dispensed_at=None,
            patient_id=uuid4(),
        )
        broadcast_prescription_updated(prescription)

    def test_broadcast_lab_order_updated(self):
        lab_order = SimpleNamespace(
            id=uuid4(),
            status="issued",
            items=SimpleNamespace(count=lambda: 2),
            expires_at=None,
            fully_completed_at=None,
            patient_id=uuid4(),
        )
        broadcast_lab_order_updated(lab_order)

    def test_broadcast_lab_result_released(self):
        lab_result = SimpleNamespace(
            id=uuid4(),
            lab_order_id=uuid4(),
            status="released",
            released_at=None,
            lab_order=SimpleNamespace(patient_id=uuid4()),
        )
        broadcast_lab_result_released(lab_result)
