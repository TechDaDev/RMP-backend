from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
	ConsultationDuration,
	ConsultationStatus,
	DoctorRecommendationType,
	MedicalSpecialty,
	MessageSenderRole,
	SeverityLevel,
	UserType,
	VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.messaging.models import ConsultationMessage, MessageAttachment
from apps.profiles.models import DoctorProfile, LaboratorianProfile, PatientProfile, PharmacistProfile, UserProfile

User = get_user_model()


def auth_client(user):
	client = APIClient()
	token = str(RefreshToken.for_user(user).access_token)
	client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
	return client


def create_user(email, user_type=UserType.PATIENT):
	user = User.objects.create_user(
		email=email,
		password="StrongPass1!",
		first_name="Test",
		last_name="User",
		user_type=user_type,
		is_active=True,
	)
	UserProfile.objects.create(user=user)
	if user_type == UserType.PATIENT:
		PatientProfile.objects.create(user=user)
	elif user_type == UserType.DOCTOR:
		DoctorProfile.objects.create(
			user=user,
			specialty=MedicalSpecialty.CARDIOLOGY,
			verification_status=VerificationStatus.APPROVED,
		)
	elif user_type == UserType.PHARMACIST:
		PharmacistProfile.objects.create(user=user)
	elif user_type == UserType.LABORATORIAN:
		LaboratorianProfile.objects.create(user=user)
	return user


def create_consultation(patient, doctor=None, status=ConsultationStatus.ACCEPTED):
	return Consultation.objects.create(
		patient=patient,
		assigned_doctor=doctor,
		status=status,
		recommended_specialty=MedicalSpecialty.CARDIOLOGY,
		selected_specialty=MedicalSpecialty.CARDIOLOGY,
		duration=ConsultationDuration.ONE_TO_THREE_DAYS,
		severity=SeverityLevel.MODERATE,
		accepted_at=timezone.now() if status in [ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED, ConsultationStatus.CLOSED] else None,
	)


class MessagingTests(TestCase):
	def setUp(self):
		self.patient = create_user("p@example.com", UserType.PATIENT)
		self.patient2 = create_user("p2@example.com", UserType.PATIENT)
		self.doctor = create_user("d@example.com", UserType.DOCTOR)
		self.doctor2 = create_user("d2@example.com", UserType.DOCTOR)
		self.pharmacist = create_user("ph@example.com", UserType.PHARMACIST)
		self.laboratorian = create_user("lab@example.com", UserType.LABORATORIAN)

		self.patient_client = auth_client(self.patient)
		self.patient2_client = auth_client(self.patient2)
		self.doctor_client = auth_client(self.doctor)
		self.doctor2_client = auth_client(self.doctor2)
		self.pharmacist_client = auth_client(self.pharmacist)
		self.laboratorian_client = auth_client(self.laboratorian)

		self.consultation = create_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)

	def msg_url(self, consultation=None):
		consultation = consultation or self.consultation
		return f"/api/consultations/{consultation.id}/messages/"

	def mark_read_url(self, consultation=None):
		consultation = consultation or self.consultation
		return f"/api/consultations/{consultation.id}/messages/mark-read/"

	# Message creation
	def test_patient_can_send_message_after_accepted(self):
		resp = self.patient_client.post(self.msg_url(), {"body": "Hello doctor"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

	def test_assigned_doctor_can_send_message_after_accepted(self):
		resp = self.doctor_client.post(self.msg_url(), {"body": "Hello patient"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

	def test_patient_cannot_send_message_before_accepted(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.SUBMITTED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "test"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_doctor_cannot_send_message_before_accepted(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.SUBMITTED)
		resp = self.doctor_client.post(self.msg_url(c), {"body": "test"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_cannot_send_message_to_closed(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.CLOSED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "test"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_cannot_send_empty_message_without_attachment(self):
		resp = self.patient_client.post(self.msg_url(), {"body": "   "}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

	def test_sender_is_set_from_request_user_and_role_matches(self):
		self.doctor_client.post(self.msg_url(), {"body": "doctor msg"}, format="json")
		msg = ConsultationMessage.objects.latest("created_at")
		self.assertEqual(msg.sender_id, self.doctor.id)
		self.assertEqual(msg.sender_role, MessageSenderRole.DOCTOR)

	def test_audit_log_created_when_message_sent(self):
		self.patient_client.post(self.msg_url(), {"body": "audit"}, format="json")
		self.assertTrue(AuditLog.objects.filter(action="consultation_message_created").exists())

	# Message listing
	def test_patient_can_list_messages_for_own_consultation(self):
		ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.doctor,
			sender_role=MessageSenderRole.DOCTOR,
			body="x",
		)
		resp = self.patient_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_200_OK)

	def test_assigned_doctor_can_list_messages(self):
		resp = self.doctor_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_200_OK)

	def test_messages_ordered_by_created_at_ascending(self):
		m1 = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.patient,
			sender_role=MessageSenderRole.PATIENT,
			body="first",
		)
		m2 = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.doctor,
			sender_role=MessageSenderRole.DOCTOR,
			body="second",
		)
		resp = self.patient_client.get(self.msg_url())
		ids = [item["id"] for item in resp.data["data"]]
		self.assertEqual(ids, [str(m1.id), str(m2.id)])

	def test_patient_cannot_list_another_patient_messages(self):
		resp = self.patient2_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_unassigned_doctor_cannot_list_messages(self):
		resp = self.doctor2_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_pharmacist_cannot_list_messages(self):
		resp = self.pharmacist_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_laboratorian_cannot_list_messages(self):
		resp = self.laboratorian_client.get(self.msg_url())
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	# Read status
	def test_messages_start_unread(self):
		self.patient_client.post(self.msg_url(), {"body": "unread"}, format="json")
		msg = ConsultationMessage.objects.latest("created_at")
		self.assertFalse(msg.is_read)
		self.assertIsNone(msg.read_at)

	def test_patient_listing_marks_doctor_messages_read(self):
		msg = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.doctor,
			sender_role=MessageSenderRole.DOCTOR,
			body="doctor msg",
		)
		self.patient_client.get(self.msg_url())
		msg.refresh_from_db()
		self.assertTrue(msg.is_read)
		self.assertIsNotNone(msg.read_at)

	def test_doctor_listing_marks_patient_messages_read(self):
		msg = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.patient,
			sender_role=MessageSenderRole.PATIENT,
			body="patient msg",
		)
		self.doctor_client.get(self.msg_url())
		msg.refresh_from_db()
		self.assertTrue(msg.is_read)

	def test_own_messages_not_marked_read_by_listing(self):
		msg = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.patient,
			sender_role=MessageSenderRole.PATIENT,
			body="mine",
		)
		self.patient_client.get(self.msg_url())
		msg.refresh_from_db()
		self.assertFalse(msg.is_read)

	def test_mark_read_endpoint_marks_other_messages_only(self):
		doctor_msg = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.doctor,
			sender_role=MessageSenderRole.DOCTOR,
			body="d",
		)
		patient_msg = ConsultationMessage.objects.create(
			consultation=self.consultation,
			sender=self.patient,
			sender_role=MessageSenderRole.PATIENT,
			body="p",
		)
		resp = self.patient_client.post(self.mark_read_url(), {}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_200_OK)
		doctor_msg.refresh_from_db()
		patient_msg.refresh_from_db()
		self.assertTrue(doctor_msg.is_read)
		self.assertFalse(patient_msg.is_read)

	# Attachments
	def test_patient_can_create_message_with_attachment(self):
		file_obj = SimpleUploadedFile("report.pdf", b"file-content", content_type="application/pdf")
		resp = self.patient_client.post(self.msg_url(), {"attachments": [file_obj]}, format="multipart")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
		self.assertTrue(MessageAttachment.objects.exists())

	def test_doctor_can_create_message_with_attachment(self):
		file_obj = SimpleUploadedFile("xray.png", b"binary", content_type="image/png")
		resp = self.doctor_client.post(self.msg_url(), {"attachments": [file_obj]}, format="multipart")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

	def test_attachment_uploaded_by_is_sender_and_original_name_stored(self):
		file_obj = SimpleUploadedFile("lab-result.txt", b"abc", content_type="text/plain")
		self.patient_client.post(self.msg_url(), {"attachments": [file_obj]}, format="multipart")
		att = MessageAttachment.objects.latest("created_at")
		self.assertEqual(att.uploaded_by_id, self.patient.id)
		self.assertEqual(att.original_name, "lab-result.txt")

	def test_audit_log_metadata_includes_attachment_count(self):
		file_obj = SimpleUploadedFile("a.txt", b"a", content_type="text/plain")
		self.patient_client.post(self.msg_url(), {"attachments": [file_obj]}, format="multipart")
		log = AuditLog.objects.filter(action="consultation_message_created").latest("created_at")
		self.assertEqual(log.metadata.get("attachment_count"), 1)

	# Consultation status rules
	def test_messages_allowed_when_accepted(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "ok"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

	def test_messages_allowed_when_doctor_responded(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.DOCTOR_RESPONDED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "ok"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

	def test_messages_not_allowed_when_submitted(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.SUBMITTED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "no"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_messages_not_allowed_when_closed(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.CLOSED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "no"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_messages_not_allowed_when_cancelled(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.CANCELLED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "no"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

	def test_messages_not_allowed_when_rejected(self):
		c = create_consultation(self.patient, self.doctor, ConsultationStatus.REJECTED)
		resp = self.patient_client.post(self.msg_url(c), {"body": "no"}, format="json")
		self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
