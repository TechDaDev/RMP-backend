from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
    ConsultationStatus,
    MedicalSpecialty,
    PrescriptionItemStatus,
    PrescriptionStatus,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.profiles.models import DoctorProfile, PatientProfile, PharmacistProfile, UserProfile

from .models import DispensingRecord, Prescription, PrescriptionItem

User = get_user_model()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_patient(email="patient@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Pat", last_name="Ient",
        user_type=UserType.PATIENT, is_active=True,
    )
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def create_doctor(email="doctor@example.com", approved=True):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Doc", last_name="Tor",
        user_type=UserType.DOCTOR, is_active=True,
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
        email=email, password="StrongPass1!", first_name="Phar", last_name="Mist",
        user_type=UserType.PHARMACIST, is_active=True,
    )
    UserProfile.objects.create(user=user)
    PharmacistProfile.objects.create(
        user=user,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def create_laboratorian(email="lab@example.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass1!", first_name="Lab", last_name="Tech",
        user_type=UserType.LABORATORIAN, is_active=True,
    )
    UserProfile.objects.create(user=user)
    return user


def create_accepted_consultation(patient, doctor):
    c = Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=ConsultationStatus.ACCEPTED,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        duration="less_than_24_hours",
        severity="mild",
    )
    return c


ITEM_PAYLOAD = {
    "medication_name": "Amoxicillin",
    "strength": "500mg",
    "dosage": "1 capsule",
    "frequency": "3 times daily",
    "duration": "7 days",
    "route": "oral",
    "quantity": "21 capsules",
    "instructions": "After food",
}


# ──────────────────────────────────────────────
# Prescription Creation Tests
# ──────────────────────────────────────────────

class PrescriptionCreationTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.consultation = create_accepted_consultation(self.patient, self.doctor)

    def _url(self):
        return f"/api/consultations/{self.consultation.id}/prescriptions/"

    def test_assigned_approved_doctor_can_create_prescription(self):
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Prescription.objects.filter(consultation=self.consultation).exists())

    def test_doctor_can_create_for_doctor_responded_consultation(self):
        self.consultation.status = ConsultationStatus.DOCTOR_RESPONDED
        self.consultation.save()
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_unassigned_doctor_cannot_create_prescription(self):
        other_doctor = create_doctor("other@example.com")
        client = auth_client(other_doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unapproved_doctor_cannot_create_prescription(self):
        unapproved = create_doctor("unapproved@example.com", approved=False)
        self.consultation.assigned_doctor = unapproved
        self.consultation.save()
        client = auth_client(unapproved)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_create_prescription(self):
        client = auth_client(self.patient)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_pharmacist_cannot_create_prescription(self):
        pharma = create_pharmacist()
        client = auth_client(pharma)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_laboratorian_cannot_create_prescription(self):
        lab = create_laboratorian()
        client = auth_client(lab)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_cannot_create_for_submitted_consultation(self):
        self.consultation.status = ConsultationStatus.SUBMITTED
        self.consultation.save()
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_with_zero_items(self):
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": []}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prescription_has_secure_qr_token(self):
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        token = resp.data["data"]["qr_token"]
        self.assertTrue(len(token) > 20)

    def test_prescription_has_expires_at(self):
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(resp.data["data"]["expires_at"])

    def test_audit_log_created_on_prescription_creation(self):
        client = auth_client(self.doctor)
        resp = client.post(self._url(), {"items": [ITEM_PAYLOAD]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AuditLog.objects.filter(action="prescription_created").exists())


# ──────────────────────────────────────────────
# Patient Safety Tests
# ──────────────────────────────────────────────

class PatientSafetyTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.other_patient = create_patient("other@example.com")
        self.doctor = create_doctor()
        self.consultation = create_accepted_consultation(self.patient, self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
            status=PrescriptionStatus.ISSUED,
        )
        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication_name="Amoxicillin",
            dosage="1 capsule",
            frequency="3x daily",
            duration="7 days",
            route="oral",
        )

    def test_patient_can_list_own_prescriptions(self):
        client = auth_client(self.patient)
        resp = client.get("/api/prescriptions/my/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

    def test_patient_detail_does_not_expose_items(self):
        client = auth_client(self.patient)
        resp = client.get(f"/api/prescriptions/my/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertNotIn("items", data)

    def test_patient_detail_does_not_expose_medication_name(self):
        client = auth_client(self.patient)
        resp = client.get(f"/api/prescriptions/my/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        import json
        text = json.dumps(resp.data["data"])
        self.assertNotIn("medication_name", text)
        self.assertNotIn("Amoxicillin", text)

    def test_patient_detail_does_not_expose_dosage(self):
        client = auth_client(self.patient)
        resp = client.get(f"/api/prescriptions/my/{self.prescription.id}/")
        data = resp.data["data"]
        self.assertNotIn("dosage", data)
        self.assertNotIn("frequency", data)
        self.assertNotIn("duration", data)
        self.assertNotIn("instructions", data)

    def test_other_patient_cannot_view_prescription(self):
        client = auth_client(self.other_patient)
        resp = client.get(f"/api/prescriptions/my/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_access_scan_endpoint(self):
        client = auth_client(self.patient)
        resp = client.post("/api/prescriptions/scan/", {"qr_token": self.prescription.qr_token}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ──────────────────────────────────────────────
# Doctor Visibility Tests
# ──────────────────────────────────────────────

class DoctorVisibilityTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.other_doctor = create_doctor("other_doc@example.com")
        self.consultation = create_accepted_consultation(self.patient, self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication_name="Paracetamol",
            dosage="1 tablet",
            frequency="4x daily",
            duration="3 days",
            route="oral",
        )

    def test_prescribing_doctor_can_view_full_prescription(self):
        client = auth_client(self.doctor)
        resp = client.get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_doctor_detail_includes_items(self):
        client = auth_client(self.doctor)
        resp = client.get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertIn("items", resp.data["data"])
        self.assertEqual(len(resp.data["data"]["items"]), 1)

    def test_doctor_detail_includes_dispensing_records(self):
        client = auth_client(self.doctor)
        resp = client.get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertIn("dispensing_records", resp.data["data"])

    def test_other_doctor_cannot_view_prescription(self):
        client = auth_client(self.other_doctor)
        resp = client.get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_can_cancel_prescription_if_no_items_dispensed(self):
        client = auth_client(self.doctor)
        resp = client.post(f"/api/prescriptions/doctor/{self.prescription.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, PrescriptionStatus.CANCELLED)

    def test_doctor_cannot_cancel_after_item_dispensed(self):
        item = self.prescription.items.first()
        item.status = PrescriptionItemStatus.DISPENSED
        item.save()
        client = auth_client(self.doctor)
        resp = client.post(f"/api/prescriptions/doctor/{self.prescription.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancellation_sets_pending_items_cancelled(self):
        client = auth_client(self.doctor)
        client.post(f"/api/prescriptions/doctor/{self.prescription.id}/cancel/")
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, PrescriptionStatus.CANCELLED)
        for item in self.prescription.items.all():
            self.assertEqual(item.status, PrescriptionItemStatus.CANCELLED)

    def test_audit_log_created_on_cancellation(self):
        client = auth_client(self.doctor)
        client.post(f"/api/prescriptions/doctor/{self.prescription.id}/cancel/")
        self.assertTrue(AuditLog.objects.filter(action="prescription_cancelled").exists())


# ──────────────────────────────────────────────
# Pharmacist QR Scan Tests
# ──────────────────────────────────────────────

class PharmacistScanTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.unapproved_pharma = create_pharmacist("unapproved_ph@example.com", approved=False)
        self.consultation = create_accepted_consultation(self.patient, self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication_name="Ibuprofen",
            dosage="1 tablet",
            frequency="3x daily",
            duration="5 days",
            route="oral",
        )

    def _scan(self, user, token=None):
        if token is None:
            token = self.prescription.qr_token
        return auth_client(user).post("/api/prescriptions/scan/", {"qr_token": token}, format="json")

    def test_approved_pharmacist_can_scan_valid_qr(self):
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unapproved_pharmacist_cannot_scan(self):
        resp = self._scan(self.unapproved_pharma)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_scan_qr(self):
        resp = self._scan(self.patient)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_cannot_scan_qr(self):
        resp = self._scan(self.doctor)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_laboratorian_cannot_scan_qr(self):
        lab = create_laboratorian()
        resp = self._scan(lab)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_scan_returns_only_pending_items(self):
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]["remaining_items"]), 1)
        self.assertFalse(resp.data["data"]["locked"])

    def test_scan_does_not_return_dispensed_items(self):
        item = self.prescription.items.first()
        item.status = PrescriptionItemStatus.DISPENSED
        item.dispensed_at = timezone.now()
        item.save()
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]["remaining_items"]), 0)

    def test_fully_dispensed_prescription_scan_returns_locked(self):
        self.prescription.status = PrescriptionStatus.FULLY_DISPENSED
        self.prescription.save()
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["locked"])
        self.assertEqual(len(resp.data["data"]["remaining_items"]), 0)

    def test_expired_prescription_scan_returns_locked(self):
        self.prescription.expires_at = timezone.now() - timezone.timedelta(days=1)
        self.prescription.save()
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["locked"])

    def test_cancelled_prescription_scan_returns_locked(self):
        self.prescription.status = PrescriptionStatus.CANCELLED
        self.prescription.cancelled_at = timezone.now()
        self.prescription.save()
        resp = self._scan(self.pharmacist)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["locked"])

    def test_audit_log_created_on_scan(self):
        self._scan(self.pharmacist)
        self.assertTrue(AuditLog.objects.filter(action="prescription_qr_scanned").exists())


# ──────────────────────────────────────────────
# Dispensing Tests
# ──────────────────────────────────────────────

class DispensingTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.pharmacist2 = create_pharmacist("pharma2@example.com")
        self.consultation = create_accepted_consultation(self.patient, self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        self.item1 = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication_name="Amoxicillin",
            dosage="1 cap",
            frequency="3x",
            duration="7d",
            route="oral",
        )
        self.item2 = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication_name="Ibuprofen",
            dosage="1 tab",
            frequency="3x",
            duration="3d",
            route="oral",
        )

    def _dispense_url(self):
        return f"/api/prescriptions/{self.prescription.id}/dispense/"

    def test_approved_pharmacist_can_dispense_pending_item(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "dispensed", "dispensed_quantity": "1 box"}]}
        resp = auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.status, PrescriptionItemStatus.DISPENSED)

    def test_dispensed_item_hidden_from_future_scan(self):
        self.item1.status = PrescriptionItemStatus.DISPENSED
        self.item1.dispensed_at = timezone.now()
        self.item1.save()
        resp = auth_client(self.pharmacist).post(
            "/api/prescriptions/scan/", {"qr_token": self.prescription.qr_token}, format="json"
        )
        remaining_ids = [str(i["id"]) for i in resp.data["data"]["remaining_items"]]
        self.assertNotIn(str(self.item1.id), remaining_ids)

    def test_unavailable_creates_record_but_item_stays_pending(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "unavailable", "note": "Not in stock"}]}
        resp = auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.status, PrescriptionItemStatus.PENDING)
        self.assertTrue(DispensingRecord.objects.filter(prescription_item=self.item1, status="unavailable").exists())

    def test_unavailable_item_remains_visible_to_other_pharmacists(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "unavailable"}]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        resp = auth_client(self.pharmacist2).post(
            "/api/prescriptions/scan/", {"qr_token": self.prescription.qr_token}, format="json"
        )
        remaining_ids = [str(i["id"]) for i in resp.data["data"]["remaining_items"]]
        self.assertIn(str(self.item1.id), remaining_ids)

    def test_partial_dispensing_sets_status_partially_dispensed(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "dispensed"}]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, PrescriptionStatus.PARTIALLY_DISPENSED)

    def test_all_items_dispensed_sets_fully_dispensed(self):
        payload = {"items": [
            {"prescription_item_id": str(self.item1.id), "status": "dispensed"},
            {"prescription_item_id": str(self.item2.id), "status": "dispensed"},
        ]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, PrescriptionStatus.FULLY_DISPENSED)

    def test_fully_dispensed_sets_fully_dispensed_at(self):
        payload = {"items": [
            {"prescription_item_id": str(self.item1.id), "status": "dispensed"},
            {"prescription_item_id": str(self.item2.id), "status": "dispensed"},
        ]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.prescription.refresh_from_db()
        self.assertIsNotNone(self.prescription.fully_dispensed_at)

    def test_cannot_dispense_already_dispensed_item(self):
        self.item1.status = PrescriptionItemStatus.DISPENSED
        self.item1.dispensed_at = timezone.now()
        self.item1.save()
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "dispensed"}]}
        resp = auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_dispense_item_from_another_prescription(self):
        other_prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        other_item = PrescriptionItem.objects.create(
            prescription=other_prescription,
            medication_name="X",
            dosage="1",
            frequency="1",
            duration="1",
            route="oral",
        )
        payload = {"items": [{"prescription_item_id": str(other_item.id), "status": "dispensed"}]}
        resp = auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_dispense_locked_prescription(self):
        self.prescription.status = PrescriptionStatus.FULLY_DISPENSED
        self.prescription.save()
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "dispensed"}]}
        resp = auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_audit_logs_created_for_item_dispensed(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "dispensed"}]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertTrue(AuditLog.objects.filter(action="prescription_item_dispensed").exists())

    def test_audit_logs_created_for_item_unavailable(self):
        payload = {"items": [{"prescription_item_id": str(self.item1.id), "status": "unavailable"}]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertTrue(AuditLog.objects.filter(action="prescription_item_unavailable").exists())

    def test_audit_log_created_for_fully_dispensed(self):
        payload = {"items": [
            {"prescription_item_id": str(self.item1.id), "status": "dispensed"},
            {"prescription_item_id": str(self.item2.id), "status": "dispensed"},
        ]}
        auth_client(self.pharmacist).post(self._dispense_url(), payload, format="json")
        self.assertTrue(AuditLog.objects.filter(action="prescription_fully_dispensed").exists())


# ──────────────────────────────────────────────
# Role Access Tests
# ──────────────────────────────────────────────

class RoleAccessTests(TestCase):

    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.lab = create_laboratorian()
        self.consultation = create_accepted_consultation(self.patient, self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )

    def test_pharmacist_cannot_view_doctor_detail(self):
        resp = auth_client(self.pharmacist).get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_view_doctor_detail(self):
        resp = auth_client(self.patient).get(f"/api/prescriptions/doctor/{self.prescription.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_laboratorian_cannot_list_prescriptions(self):
        resp = auth_client(self.lab).get("/api/prescriptions/my/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_laboratorian_cannot_scan_qr(self):
        resp = auth_client(self.lab).post("/api/prescriptions/scan/", {"qr_token": self.prescription.qr_token}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_laboratorian_cannot_dispense(self):
        resp = auth_client(self.lab).post(f"/api/prescriptions/{self.prescription.id}/dispense/", {"items": []}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
