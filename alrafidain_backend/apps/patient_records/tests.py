from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
	BloodGroup,
	ConsultationStatus,
	MedicalRecordCategory,
	MedicalRecordVerificationStatus,
	MedicalSpecialty,
	NotificationType,
	UserType,
	VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.notifications.models import Notification
from apps.profiles.models import (
	DoctorProfile,
	LaboratorianProfile,
	PatientProfile,
	PharmacistProfile,
	UserProfile,
)

from .models import BloodGroupRecord, MedicalRecordEntry, PatientMedicalRecord
from .services import get_or_create_patient_medical_record

User = get_user_model()


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


def create_pharmacist(email="pharmacist@example.com", approved=True):
	user = User.objects.create_user(
		email=email,
		password="StrongPass1!",
		first_name="Phar",
		last_name="Macist",
		user_type=UserType.PHARMACIST,
		is_active=True,
	)
	UserProfile.objects.create(user=user)
	PharmacistProfile.objects.create(
		user=user,
		verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
	)
	return user


def create_laboratorian(email="lab@example.com", approved=True):
	user = User.objects.create_user(
		email=email,
		password="StrongPass1!",
		first_name="Lab",
		last_name="Tech",
		user_type=UserType.LABORATORIAN,
		is_active=True,
	)
	UserProfile.objects.create(user=user)
	LaboratorianProfile.objects.create(
		user=user,
		verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
	)
	return user


def create_doctor_access_consultation(patient, doctor, status=ConsultationStatus.ACCEPTED):
	return Consultation.objects.create(
		patient=patient,
		assigned_doctor=doctor,
		status=status,
		selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
		duration="one_to_two_weeks",
		severity="mild",
	)


class RecordCreationTests(TestCase):
	def test_patient_medical_record_created_lazily(self):
		patient = create_patient()
		self.assertFalse(PatientMedicalRecord.objects.filter(patient=patient).exists())

		record = get_or_create_patient_medical_record(patient)
		self.assertTrue(PatientMedicalRecord.objects.filter(id=record.id).exists())
		self.assertTrue(BloodGroupRecord.objects.filter(medical_record=record).exists())

	def test_patient_registration_creates_medical_record(self):
		client = APIClient()
		response = client.post(
			"/api/accounts/register/",
			{
				"email": "newpatient@example.com",
				"password": "StrongPass1!",
				"password_confirm": "StrongPass1!",
				"first_name": "New",
				"last_name": "Patient",
				"user_type": UserType.PATIENT,
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		user = User.objects.get(email="newpatient@example.com")
		self.assertTrue(PatientMedicalRecord.objects.filter(patient=user).exists())
		record = PatientMedicalRecord.objects.get(patient=user)
		blood = BloodGroupRecord.objects.get(medical_record=record)
		self.assertEqual(blood.blood_group, BloodGroup.UNKNOWN)
		self.assertEqual(blood.verification_status, MedicalRecordVerificationStatus.UNKNOWN)

	def test_non_patient_cannot_have_patient_medical_record(self):
		doctor = create_doctor()
		with self.assertRaises(ValueError):
			get_or_create_patient_medical_record(doctor)


class PatientAccessTests(TestCase):
	def setUp(self):
		self.patient = create_patient()
		self.other_patient = create_patient(email="otherpatient@example.com")
		self.record = get_or_create_patient_medical_record(self.patient)
		self.client = auth_client(self.patient)

	def test_patient_can_view_own_medical_record(self):
		response = self.client.get("/api/patient-records/my/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["data"]["patient"]["id"], str(self.patient.id))

	def test_patient_cannot_view_another_patient_medical_record(self):
		response = self.client.get(f"/api/patient-records/patients/{self.other_patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_patient_can_create_self_reported_entry(self):
		response = self.client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.ALLERGY,
				"title": "Dust allergy",
				"value": "Sneezing during spring.",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		entry = MedicalRecordEntry.objects.get(id=response.data["data"]["id"])
		self.assertEqual(entry.source_role, "patient")
		self.assertEqual(entry.verification_status, MedicalRecordVerificationStatus.SELF_REPORTED)

	def test_patient_cannot_set_verification_status_manually(self):
		response = self.client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.ALLERGY,
				"title": "Dust allergy",
				"value": "Sneezing during spring.",
				"verification_status": MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_patient_can_deactivate_own_self_reported_entry(self):
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.ALLERGY,
			title="Pollen",
			value="Seasonal",
			source_user=self.patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.client.post(
			f"/api/patient-records/entries/{entry.id}/deactivate/",
			{"notes": "No longer relevant."},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		entry.refresh_from_db()
		self.assertFalse(entry.is_active)

	def test_patient_cannot_deactivate_doctor_confirmed_entry(self):
		doctor = create_doctor(email="doc2@example.com")
		create_doctor_access_consultation(self.patient, doctor)
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.CHRONIC_CONDITION,
			title="Hypertension",
			value="Clinically diagnosed",
			source_user=doctor,
			source_role="doctor",
			verification_status=MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
			verified_by=doctor,
		)
		response = self.client.post(f"/api/patient-records/entries/{entry.id}/deactivate/", {}, format="json")
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DoctorAccessTests(TestCase):
	def setUp(self):
		self.patient = create_patient()
		self.other_patient = create_patient(email="p2@example.com")
		self.doctor = create_doctor()
		self.unapproved_doctor = create_doctor(email="pendingdoc@example.com", approved=False)
		self.record = get_or_create_patient_medical_record(self.patient)
		self.doctor_client = auth_client(self.doctor)
		self.unapproved_client = auth_client(self.unapproved_doctor)

	def test_approved_assigned_doctor_can_view_patient_record_after_accepted_consultation(self):
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)
		response = self.doctor_client.get(f"/api/patient-records/patients/{self.patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)

	def test_doctor_cannot_view_unrelated_patient_record(self):
		response = self.doctor_client.get(f"/api/patient-records/patients/{self.other_patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_unapproved_doctor_cannot_view_patient_record(self):
		create_doctor_access_consultation(self.patient, self.unapproved_doctor, ConsultationStatus.ACCEPTED)
		response = self.unapproved_client.get(f"/api/patient-records/patients/{self.patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_doctor_can_create_doctor_confirmed_entry(self):
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)
		response = self.doctor_client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.CHRONIC_CONDITION,
				"title": "Hypertension",
				"value": "Clinically confirmed.",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		entry = MedicalRecordEntry.objects.get(id=response.data["data"]["id"])
		self.assertEqual(entry.verification_status, MedicalRecordVerificationStatus.DOCTOR_CONFIRMED)
		self.assertEqual(entry.verified_by_id, self.doctor.id)

	def test_doctor_can_confirm_self_reported_entry(self):
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.DOCTOR_RESPONDED)
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.ALLERGY,
			title="Allergy",
			value="Patient report",
			source_user=self.patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.doctor_client.post(
			f"/api/patient-records/entries/{entry.id}/confirm/",
			{
				"verification_status": MedicalRecordVerificationStatus.DOCTOR_CONFIRMED,
				"notes": "Confirmed during consultation.",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		entry.refresh_from_db()
		self.assertEqual(entry.verification_status, MedicalRecordVerificationStatus.DOCTOR_CONFIRMED)

	def test_doctor_can_reject_self_reported_entry(self):
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.CLOSED)
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.ALLERGY,
			title="Allergy",
			value="Patient report",
			source_user=self.patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.doctor_client.post(
			f"/api/patient-records/entries/{entry.id}/confirm/",
			{
				"verification_status": MedicalRecordVerificationStatus.REJECTED,
				"notes": "Inconsistent with clinical review.",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		entry.refresh_from_db()
		self.assertEqual(entry.verification_status, MedicalRecordVerificationStatus.REJECTED)

	def test_doctor_cannot_confirm_entry_for_unrelated_patient(self):
		entry = MedicalRecordEntry.objects.create(
			medical_record=get_or_create_patient_medical_record(self.other_patient),
			category=MedicalRecordCategory.ALLERGY,
			title="Allergy",
			value="Patient report",
			source_user=self.other_patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.doctor_client.post(
			f"/api/patient-records/entries/{entry.id}/confirm/",
			{"verification_status": MedicalRecordVerificationStatus.DOCTOR_CONFIRMED},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BloodGroupTests(TestCase):
	def setUp(self):
		self.patient = create_patient()
		self.doctor = create_doctor()
		self.pharmacist = create_pharmacist()
		self.lab = create_laboratorian(approved=True)
		self.pending_lab = create_laboratorian(email="pendinglab@example.com", approved=False)

		self.record = get_or_create_patient_medical_record(self.patient)

		self.patient_client = auth_client(self.patient)
		self.doctor_client = auth_client(self.doctor)
		self.pharmacist_client = auth_client(self.pharmacist)
		self.lab_client = auth_client(self.lab)
		self.pending_lab_client = auth_client(self.pending_lab)

	def test_patient_can_set_own_blood_group_as_self_reported(self):
		response = self.patient_client.post(
			f"/api/patient-records/{self.record.id}/blood-group/",
			{"blood_group": BloodGroup.O_POSITIVE, "notes": "Home test report"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		blood = BloodGroupRecord.objects.get(medical_record=self.record)
		self.assertEqual(blood.verification_status, MedicalRecordVerificationStatus.SELF_REPORTED)

	def test_doctor_can_set_blood_group_as_doctor_confirmed_if_doctor_has_access(self):
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)
		response = self.doctor_client.post(
			f"/api/patient-records/{self.record.id}/blood-group/",
			{"blood_group": BloodGroup.A_POSITIVE, "notes": "Confirmed clinically"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		blood = BloodGroupRecord.objects.get(medical_record=self.record)
		self.assertEqual(blood.verification_status, MedicalRecordVerificationStatus.DOCTOR_CONFIRMED)

	def test_approved_laboratorian_can_verify_blood_group_as_laboratory_confirmed(self):
		response = self.lab_client.post(
			f"/api/patient-records/patients/{self.patient.id}/blood-group/verify/",
			{"blood_group": BloodGroup.AB_NEGATIVE, "notes": "Verified by lab test"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		blood = BloodGroupRecord.objects.get(medical_record=self.record)
		self.assertEqual(blood.verification_status, MedicalRecordVerificationStatus.LABORATORY_CONFIRMED)

	def test_unapproved_laboratorian_cannot_verify_blood_group(self):
		response = self.pending_lab_client.post(
			f"/api/patient-records/patients/{self.patient.id}/blood-group/verify/",
			{"blood_group": BloodGroup.O_NEGATIVE},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_pharmacist_cannot_set_blood_group(self):
		response = self.pharmacist_client.post(
			f"/api/patient-records/{self.record.id}/blood-group/",
			{"blood_group": BloodGroup.B_POSITIVE},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_blood_group_is_not_required_at_registration(self):
		blood = BloodGroupRecord.objects.get(medical_record=self.record)
		self.assertEqual(blood.blood_group, BloodGroup.UNKNOWN)


class RoleRestrictionTests(TestCase):
	def setUp(self):
		self.patient = create_patient()
		self.record = get_or_create_patient_medical_record(self.patient)
		self.pharmacist = create_pharmacist()
		self.laboratorian = create_laboratorian()
		self.pharmacist_client = auth_client(self.pharmacist)
		self.laboratorian_client = auth_client(self.laboratorian)

	def test_pharmacist_cannot_view_medical_record(self):
		response = self.pharmacist_client.get(f"/api/patient-records/patients/{self.patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_pharmacist_cannot_create_medical_record_entry(self):
		response = self.pharmacist_client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.GENERAL_NOTE,
				"title": "Note",
				"value": "Pharmacist note",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_laboratorian_cannot_view_full_medical_record(self):
		response = self.laboratorian_client.get(f"/api/patient-records/patients/{self.patient.id}/")
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_laboratorian_cannot_create_generic_medical_record_entry(self):
		response = self.laboratorian_client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.GENERAL_NOTE,
				"title": "Lab note",
				"value": "Should not be allowed",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class NotificationAndAuditTests(TestCase):
	def setUp(self):
		self.patient = create_patient()
		self.doctor = create_doctor()
		self.laboratorian = create_laboratorian()
		self.record = get_or_create_patient_medical_record(self.patient)
		create_doctor_access_consultation(self.patient, self.doctor, ConsultationStatus.ACCEPTED)
		self.doctor_client = auth_client(self.doctor)
		self.lab_client = auth_client(self.laboratorian)

	def test_medical_record_creation_creates_audit_log(self):
		patient = create_patient(email="auditpatient@example.com")
		self.assertFalse(PatientMedicalRecord.objects.filter(patient=patient).exists())
		record = get_or_create_patient_medical_record(patient)
		self.assertTrue(AuditLog.objects.filter(action="medical_record_created", target_id=str(record.id)).exists())

	def test_entry_creation_creates_audit_log(self):
		response = self.doctor_client.post(
			f"/api/patient-records/{self.record.id}/entries/",
			{
				"category": MedicalRecordCategory.CHRONIC_CONDITION,
				"title": "Hypertension",
				"value": "Confirmed",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		entry_id = response.data["data"]["id"]
		self.assertTrue(AuditLog.objects.filter(action="medical_record_entry_created", target_id=entry_id).exists())

	def test_doctor_confirmation_creates_audit_log_and_patient_notification(self):
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.ALLERGY,
			title="Allergy",
			value="patient report",
			source_user=self.patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.doctor_client.post(
			f"/api/patient-records/entries/{entry.id}/confirm/",
			{"verification_status": MedicalRecordVerificationStatus.DOCTOR_CONFIRMED},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(AuditLog.objects.filter(action="medical_record_entry_confirmed", target_id=str(entry.id)).exists())
		self.assertTrue(
			Notification.objects.filter(
				recipient=self.patient,
				notification_type=NotificationType.MEDICAL_RECORD,
				data__entry_id=str(entry.id),
			).exists()
		)

	def test_doctor_rejection_creates_audit_log_and_patient_notification(self):
		entry = MedicalRecordEntry.objects.create(
			medical_record=self.record,
			category=MedicalRecordCategory.ALLERGY,
			title="Allergy",
			value="patient report",
			source_user=self.patient,
			source_role="patient",
			verification_status=MedicalRecordVerificationStatus.SELF_REPORTED,
		)
		response = self.doctor_client.post(
			f"/api/patient-records/entries/{entry.id}/confirm/",
			{"verification_status": MedicalRecordVerificationStatus.REJECTED},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(AuditLog.objects.filter(action="medical_record_entry_rejected", target_id=str(entry.id)).exists())
		self.assertTrue(
			Notification.objects.filter(
				recipient=self.patient,
				notification_type=NotificationType.MEDICAL_RECORD,
				data__entry_id=str(entry.id),
			).exists()
		)

	def test_blood_group_update_creates_audit_log_and_patient_notification(self):
		response = self.doctor_client.post(
			f"/api/patient-records/{self.record.id}/blood-group/",
			{"blood_group": BloodGroup.B_NEGATIVE, "notes": "Updated clinically"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(AuditLog.objects.filter(action="blood_group_updated").exists())
		self.assertTrue(
			Notification.objects.filter(
				recipient=self.patient,
				notification_type=NotificationType.MEDICAL_RECORD,
				data__record_id=str(self.record.id),
			).exists()
		)

	def test_laboratorian_verification_creates_audit_log_and_patient_notification(self):
		response = self.lab_client.post(
			f"/api/patient-records/patients/{self.patient.id}/blood-group/verify/",
			{"blood_group": BloodGroup.O_POSITIVE, "notes": "Verified in laboratory"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(AuditLog.objects.filter(action="blood_group_verified").exists())
		self.assertTrue(
			Notification.objects.filter(
				recipient=self.patient,
				notification_type=NotificationType.MEDICAL_RECORD,
				data__record_id=str(self.record.id),
				data__verification_status=MedicalRecordVerificationStatus.LABORATORY_CONFIRMED,
			).exists()
		)
