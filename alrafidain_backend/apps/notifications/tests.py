from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    MedicalSpecialty,
    NotificationPriority,
    NotificationType,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.profiles.models import DoctorProfile, PatientProfile, PharmacistProfile, UserProfile

from .models import Notification
from .services import create_notification, notify_many

User = get_user_model()


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


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


def create_doctor(email="doctor@example.com", approved=True):
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
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def create_pharmacist(email="pharma@example.com", approved=True):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Phar",
        last_name="Ma",
        user_type=UserType.PHARMACIST,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    PharmacistProfile.objects.create(
        user=user,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def create_accepted_consultation(patient, doctor):
    return Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        status="accepted",
        duration="1_week",
        severity="mild",
    )


def create_pending_prescription(consultation, doctor, patient):
    prescription = Prescription.objects.create(
        consultation=consultation,
        doctor=doctor,
        patient=patient,
    )
    PrescriptionItem.objects.create(
        prescription=prescription,
        medication_name="Aspirin",
        dosage="500mg",
        frequency="Once daily",
        duration="7 days",
    )
    return prescription


# ─────────────────────────────────────────
# Model & Service Tests
# ─────────────────────────────────────────


class NotificationModelTest(TestCase):
    def setUp(self):
        self.user = create_patient()

    def test_create_notification_service(self):
        n = create_notification(
            recipient=self.user,
            notification_type=NotificationType.SYSTEM,
            title="Hello",
            message="World",
        )
        self.assertEqual(n.recipient, self.user)
        self.assertEqual(n.notification_type, NotificationType.SYSTEM)
        self.assertFalse(n.is_read)
        self.assertIsNone(n.read_at)

    def test_create_notification_default_priority_normal(self):
        n = create_notification(
            recipient=self.user,
            notification_type=NotificationType.ACCOUNT,
            title="T",
            message="M",
        )
        self.assertEqual(n.priority, NotificationPriority.NORMAL)

    def test_create_notification_with_data(self):
        n = create_notification(
            recipient=self.user,
            notification_type=NotificationType.CONSULTATION,
            title="T",
            message="M",
            data={"consultation_id": "abc"},
        )
        self.assertEqual(n.data["consultation_id"], "abc")

    def test_create_notification_requires_recipient(self):
        with self.assertRaises(ValueError):
            create_notification(
                recipient=None, notification_type=NotificationType.SYSTEM, title="T", message="M"
            )

    def test_mark_as_read(self):
        n = create_notification(
            recipient=self.user, notification_type=NotificationType.SYSTEM, title="T", message="M"
        )
        self.assertFalse(n.is_read)
        n.mark_as_read()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_mark_as_read_idempotent(self):
        n = create_notification(
            recipient=self.user, notification_type=NotificationType.SYSTEM, title="T", message="M"
        )
        n.mark_as_read()
        first_read_at = n.read_at
        n.mark_as_read()
        self.assertEqual(n.read_at, first_read_at)

    def test_notify_many(self):
        user2 = create_patient(email="p2@example.com")
        notify_many(
            recipients=[self.user, user2],
            notification_type=NotificationType.SYSTEM,
            title="Broadcast",
            message="Hello all",
        )
        self.assertEqual(
            Notification.objects.filter(notification_type=NotificationType.SYSTEM).count(), 2
        )


# ─────────────────────────────────────────
# API Tests
# ─────────────────────────────────────────


class NotificationListAPITest(TestCase):
    def setUp(self):
        self.user = create_patient()
        self.other = create_patient(email="other@example.com")
        self.client = auth_client(self.user)
        create_notification(self.user, NotificationType.SYSTEM, "A", "msg A")
        create_notification(self.user, NotificationType.CONSULTATION, "B", "msg B")
        create_notification(self.other, NotificationType.SYSTEM, "C", "other msg")

    def test_list_returns_only_own_notifications(self):
        r = self.client.get("/api/notifications/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["success"])
        self.assertEqual(len(r.data["data"]), 2)

    def test_filter_by_is_read_false(self):
        r = self.client.get("/api/notifications/?is_read=false")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["data"]), 2)

    def test_filter_by_is_read_true(self):
        Notification.objects.filter(recipient=self.user).update(is_read=True)
        r = self.client.get("/api/notifications/?is_read=true")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["data"]), 2)

    def test_filter_by_notification_type(self):
        r = self.client.get(
            f"/api/notifications/?notification_type={NotificationType.CONSULTATION}"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["data"]), 1)

    def test_unauthenticated_returns_401(self):
        r = APIClient().get("/api/notifications/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


class UnreadCountAPITest(TestCase):
    def setUp(self):
        self.user = create_patient()
        self.client = auth_client(self.user)

    def test_unread_count_zero(self):
        r = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["unread_count"], 0)

    def test_unread_count_increments(self):
        create_notification(self.user, NotificationType.SYSTEM, "T", "M")
        create_notification(self.user, NotificationType.SYSTEM, "T2", "M2")
        r = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(r.data["data"]["unread_count"], 2)

    def test_unread_count_after_mark_read(self):
        n = create_notification(self.user, NotificationType.SYSTEM, "T", "M")
        n.mark_as_read()
        r = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(r.data["data"]["unread_count"], 0)


class MarkNotificationReadAPITest(TestCase):
    def setUp(self):
        self.user = create_patient()
        self.other = create_patient(email="other@example.com")
        self.client = auth_client(self.user)

    def test_mark_own_notification_as_read(self):
        n = create_notification(self.user, NotificationType.SYSTEM, "T", "M")
        r = self.client.post(f"/api/notifications/{n.id}/mark-read/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_cannot_mark_others_notification(self):
        n = create_notification(self.other, NotificationType.SYSTEM, "T", "M")
        r = self.client.post(f"/api/notifications/{n.id}/mark-read/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_mark_nonexistent_notification_returns_404(self):
        import uuid

        r = self.client.post(f"/api/notifications/{uuid.uuid4()}/mark-read/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class MarkAllNotificationsReadAPITest(TestCase):
    def setUp(self):
        self.user = create_patient()
        self.client = auth_client(self.user)

    def test_mark_all_read(self):
        create_notification(self.user, NotificationType.SYSTEM, "A", "M")
        create_notification(self.user, NotificationType.SYSTEM, "B", "M")
        r = self.client.post("/api/notifications/mark-all-read/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["updated_count"], 2)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)

    def test_mark_all_read_does_not_affect_others(self):
        other = create_patient(email="other2@example.com")
        create_notification(other, NotificationType.SYSTEM, "C", "M")
        self.client.post("/api/notifications/mark-all-read/")
        self.assertFalse(Notification.objects.get(recipient=other).is_read)

    def test_mark_all_read_already_read_returns_zero(self):
        n = create_notification(self.user, NotificationType.SYSTEM, "A", "M")
        n.mark_as_read()
        r = self.client.post("/api/notifications/mark-all-read/")
        self.assertEqual(r.data["data"]["updated_count"], 0)


# ─────────────────────────────────────────
# Workflow Integration Tests
# ─────────────────────────────────────────


class ConsultationNotificationIntegrationTest(TestCase):
    """Test that consultation workflow steps create appropriate notifications."""

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()

    def test_prescription_issued_notifies_patient(self):
        """Test that patient is notified when doctor issues a prescription."""
        from apps.prescriptions.services import create_prescription

        consultation = create_accepted_consultation(self.patient, self.doctor)
        create_prescription(
            consultation,
            self.doctor,
            [
                {
                    "medication_name": "Aspirin",
                    "dosage": "500mg",
                    "frequency": "Once daily",
                    "duration": "7 days",
                }
            ],
        )
        notif = Notification.objects.filter(
            recipient=self.patient,
            notification_type=NotificationType.PRESCRIPTION,
            title="Prescription issued",
        ).first()
        self.assertIsNotNone(notif)
        # Ensure no medication details in data
        for forbidden in ("medication_name", "dosage", "frequency", "duration", "instructions"):
            self.assertNotIn(forbidden, notif.data)

    def test_patient_receives_doctor_dispensing_notifications(self):
        """Test that patient is notified when prescription is fully dispensed."""
        from apps.prescriptions.services import create_prescription, dispense_prescription_items

        consultation = create_accepted_consultation(self.patient, self.doctor)
        pharmacist = create_pharmacist()
        prescription = create_prescription(
            consultation,
            self.doctor,
            [
                {
                    "medication_name": "Aspirin",
                    "dosage": "500mg",
                    "frequency": "Once daily",
                    "duration": "7 days",
                }
            ],
        )
        item = prescription.items.first()
        dispense_prescription_items(
            prescription,
            pharmacist,
            [
                {
                    "prescription_item_id": item.id,
                    "status": "dispensed",
                    "dispensed_quantity": "1 box",
                }
            ],
        )
        # Check doctor is notified of dispensing
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor,
                notification_type=NotificationType.DISPENSING,
                title="Medication item dispensed",
            ).exists()
        )
        # Check patient is notified of full dispensing
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.patient,
                notification_type=NotificationType.DISPENSING,
                title="Prescription fully dispensed",
            ).exists()
        )
        # Ensure patient notification doesn't have medication details
        notif = Notification.objects.get(
            recipient=self.patient,
            notification_type=NotificationType.DISPENSING,
            title="Prescription fully dispensed",
        )
        for forbidden in ("medication_name", "dosage", "frequency", "duration", "instructions"):
            self.assertNotIn(forbidden, notif.data)


class MessagingNotificationIntegrationTest(TestCase):
    """Test that messaging creates notifications for consultation parties."""

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.consultation = create_accepted_consultation(self.patient, self.doctor)

    def test_patient_message_notifies_doctor(self):
        """Test that doctor is notified when patient sends a message."""
        from apps.messaging.services import create_consultation_message

        create_consultation_message(self.consultation, self.patient, body="I have a question.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor,
                notification_type=NotificationType.MESSAGE,
                title="New patient message",
            ).exists()
        )

    def test_doctor_message_notifies_patient(self):
        """Test that patient is notified when doctor sends a message."""
        from apps.messaging.services import create_consultation_message

        create_consultation_message(self.consultation, self.doctor, body="Please follow up.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.patient,
                notification_type=NotificationType.MESSAGE,
                title="New doctor message",
            ).exists()
        )
