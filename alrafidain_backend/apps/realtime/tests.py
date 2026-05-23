"""Tests for realtime permissions and broadcast services."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    DoctorAIAssistantMessageStatus,
    DoctorAIAssistantSafetyLevel,
    DoctorAIAssistantTriggerType,
    MedicalSpecialty,
    MessageSenderRole,
    MessageType,
    NotificationType,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification
from apps.profiles.models import DoctorProfile, PatientProfile, UserProfile
from apps.rag.models import DoctorAIAssistantMessage
from config.asgi import application

from .permissions import can_connect_consultation_messages, can_connect_user_socket
from .services import (
    broadcast_consultation_updated,
    broadcast_doctor_ai_message_created,
    broadcast_doctor_ai_message_updated,
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

    @patch("apps.realtime.services.send_to_group_safe")
    def test_broadcast_message_created_matches_contract(self, send_to_group_safe):
        patient = create_patient("contract-patient@example.com")
        doctor = create_doctor("contract-doctor@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        message = ConsultationMessage.objects.create(
            consultation=consultation,
            sender=patient,
            sender_role=MessageSenderRole.PATIENT,
            message_type=MessageType.TEXT,
            body="Contract message",
        )

        broadcast_message_created(message)

        send_to_group_safe.assert_called_once()
        group_name, event_data = send_to_group_safe.call_args.args
        self.assertEqual(group_name, f"consultation_{consultation.id}")
        self.assertEqual(event_data["type"], "chat.message.created")
        self.assertEqual(event_data["consultation_id"], str(consultation.id))
        self.assertEqual(
            set(event_data["message"].keys()),
            {
                "id",
                "sender",
                "sender_role",
                "message_type",
                "body",
                "attachments",
                "is_read",
                "created_at",
            },
        )

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

    @patch("apps.realtime.services.send_to_group_safe")
    def test_broadcast_doctor_ai_message_created_contract(self, send_to_group_safe):
        patient = create_patient("ai-contract-patient@example.com")
        doctor = create_doctor("ai-contract-doctor@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        ai_message = DoctorAIAssistantMessage.objects.create(
            consultation=consultation,
            doctor=doctor,
            patient=patient,
            trigger_type=DoctorAIAssistantTriggerType.MEDICAL_REPORT_CASE_UPDATE,
            status=DoctorAIAssistantMessageStatus.UNREAD,
            safety_level=DoctorAIAssistantSafetyLevel.DOCTOR_ONLY,
            title="AI case update",
            body="Doctor-only AI response.",
            summary={
                "rag_response_id": str(uuid4()),
                "rag_query_id": str(uuid4()),
                "service_context": "report_case_update",
                "source_count": 1,
                "document_titles": ["Guideline A"],
                "confidence": None,
                "fallback_reason": None,
                "source_report_id": str(uuid4()),
                "linked_medical_record_entry_id": str(uuid4()),
            },
            source_metadata={"prompt_text": "must-not-leak", "raw_response": {"k": "v"}},
        )

        broadcast_doctor_ai_message_created(ai_message)

        send_to_group_safe.assert_called_once()
        group_name, event_data = send_to_group_safe.call_args.args
        self.assertEqual(group_name, f"user_{doctor.id}")
        self.assertNotEqual(group_name, f"user_{patient.id}")
        self.assertNotEqual(group_name, f"consultation_{consultation.id}")
        self.assertEqual(event_data["type"], "doctor_ai.message.created")
        self.assertIn("message", event_data)
        self.assertEqual(event_data["message"]["id"], str(ai_message.id))
        self.assertEqual(event_data["message"]["consultation"], str(consultation.id))
        self.assertNotIn("prompt_text", event_data["message"])
        self.assertNotIn("raw_response", event_data["message"])
        self.assertNotIn("source_metadata", event_data["message"])

    @patch("apps.realtime.services.send_to_group_safe")
    def test_broadcast_doctor_ai_message_updated_contract(self, send_to_group_safe):
        patient = create_patient("ai-update-patient@example.com")
        doctor = create_doctor("ai-update-doctor@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        ai_message = DoctorAIAssistantMessage.objects.create(
            consultation=consultation,
            doctor=doctor,
            patient=patient,
            trigger_type=DoctorAIAssistantTriggerType.MEDICAL_REPORT_CASE_UPDATE,
            status=DoctorAIAssistantMessageStatus.READ,
            safety_level=DoctorAIAssistantSafetyLevel.DOCTOR_ONLY,
            title="AI case update",
            body="Doctor-only AI response.",
        )

        broadcast_doctor_ai_message_updated(ai_message)

        send_to_group_safe.assert_called_once()
        group_name, event_data = send_to_group_safe.call_args.args
        self.assertEqual(group_name, f"user_{doctor.id}")
        self.assertEqual(event_data["type"], "doctor_ai.message.updated")
        self.assertEqual(event_data["message"]["id"], str(ai_message.id))


class DoctorAiUserSocketDeliveryTests(TransactionTestCase):
    def test_doctor_ai_event_reaches_doctor_user_socket_not_patient_user_socket(self):
        patient = create_patient("socket-ai-patient@example.com")
        doctor = create_doctor("socket-ai-doctor@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)
        ai_message = DoctorAIAssistantMessage.objects.create(
            consultation=consultation,
            doctor=doctor,
            patient=patient,
            trigger_type=DoctorAIAssistantTriggerType.MEDICAL_REPORT_CASE_UPDATE,
            status=DoctorAIAssistantMessageStatus.UNREAD,
            safety_level=DoctorAIAssistantSafetyLevel.DOCTOR_ONLY,
            title="AI case update",
            body="Doctor-only AI response.",
            summary={"service_context": "report_case_update"},
        )

        patient_token = str(RefreshToken.for_user(patient).access_token)
        doctor_token = str(RefreshToken.for_user(doctor).access_token)

        async def scenario():
            patient_socket = WebsocketCommunicator(
                application,
                f"/ws/user/?token={patient_token}",
            )
            doctor_socket = WebsocketCommunicator(
                application,
                f"/ws/user/?token={doctor_token}",
            )

            patient_connected, _ = await patient_socket.connect()
            doctor_connected, _ = await doctor_socket.connect()

            self.assertTrue(patient_connected)
            self.assertTrue(doctor_connected)

            try:
                await database_sync_to_async(broadcast_doctor_ai_message_created)(ai_message)

                doctor_event = await doctor_socket.receive_json_from(timeout=1)
                self.assertEqual(doctor_event["type"], "doctor_ai.message.created")
                self.assertEqual(doctor_event["message"]["id"], str(ai_message.id))

                nothing_received = await patient_socket.receive_nothing(timeout=0.3)
                self.assertTrue(nothing_received)
            finally:
                await patient_socket.disconnect()
                await doctor_socket.disconnect()

        async_to_sync(scenario)()


class ConsultationSocketDeliveryTests(TransactionTestCase):
    def test_message_create_broadcast_reaches_other_participant(self):
        patient = create_patient("socket-patient@example.com")
        doctor = create_doctor("socket-doctor@example.com")
        consultation = create_consultation(patient, doctor, ConsultationStatus.ACCEPTED)

        patient_token = str(RefreshToken.for_user(patient).access_token)
        doctor_token = str(RefreshToken.for_user(doctor).access_token)

        async def scenario():
            patient_socket = WebsocketCommunicator(
                application,
                f"/ws/consultations/{consultation.id}/messages/?token={patient_token}",
            )
            doctor_socket = WebsocketCommunicator(
                application,
                f"/ws/consultations/{consultation.id}/messages/?token={doctor_token}",
            )

            patient_connected, _ = await patient_socket.connect()
            doctor_connected, _ = await doctor_socket.connect()

            self.assertTrue(patient_connected)
            self.assertTrue(doctor_connected)

            try:
                from apps.messaging.services import create_consultation_message

                message = await database_sync_to_async(create_consultation_message)(
                    consultation=consultation,
                    sender=patient,
                    body="Realtime hello",
                )

                patient_event = await patient_socket.receive_json_from(timeout=1)
                doctor_event = await doctor_socket.receive_json_from(timeout=1)

                self.assertEqual(patient_event["type"], "chat.message.created")
                self.assertEqual(doctor_event["type"], "chat.message.created")
                self.assertEqual(patient_event["consultation_id"], str(consultation.id))
                self.assertEqual(doctor_event["consultation_id"], str(consultation.id))
                self.assertEqual(patient_event["message"]["id"], str(message.id))
                self.assertEqual(doctor_event["message"]["id"], str(message.id))
                self.assertEqual(patient_event["message"]["body"], "Realtime hello")
                self.assertEqual(doctor_event["message"]["body"], "Realtime hello")
            finally:
                await patient_socket.disconnect()
                await doctor_socket.disconnect()

        async_to_sync(scenario)()
