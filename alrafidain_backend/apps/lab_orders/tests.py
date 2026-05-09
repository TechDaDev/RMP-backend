import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.common.choices import (
    BloodGroup,
    ConsultationStatus,
    LabCompletionAttemptStatus,
    LabOrderItemStatus,
    LabOrderStatus,
    LabResultStatus,
    LabResultValueType,
    LabTestCategory,
    MedicalRecordSourceRole,
    MedicalRecordVerificationStatus,
    MedicalSpecialty,
    NotificationType,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.notifications.models import Notification
from apps.patient_records.models import BloodGroupRecord, MedicalRecordEntry
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)

from .models import (
    LabCompletionRecord,
    LabOrder,
    LabOrderItem,
    LabResult,
    LabResultCorrection,
    LabTestCatalog,
)

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


def create_pharmacist(email="pharma@example.com", approved=True):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Phar",
        last_name="Mist",
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


def create_consultation(patient, doctor, status=ConsultationStatus.ACCEPTED):
    return Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=status,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        duration="less_than_24_hours",
        severity="mild",
    )


def create_catalog_test(name="CBC", category=LabTestCategory.HEMATOLOGY, is_active=True):
    return LabTestCatalog.objects.create(
        name=name,
        category=category,
        default_sample_type="Blood",
        default_instructions="Standard sample handling",
        is_active=is_active,
    )


def create_lab_order_with_items(patient, doctor, consultation, item_count=2):
    lab_order = LabOrder.objects.create(consultation=consultation, doctor=doctor, patient=patient)
    for idx in range(item_count):
        LabOrderItem.objects.create(
            lab_order=lab_order,
            test_name=f"Test {idx + 1}",
            category=LabTestCategory.HEMATOLOGY,
            sample_type="Blood",
            instructions="Instruction",
        )
    return lab_order


class LabTestCatalogTests(TestCase):
    def setUp(self):
        self.user = create_patient()
        self.client = auth_client(self.user)
        create_catalog_test("CBC", LabTestCategory.HEMATOLOGY, is_active=True)
        create_catalog_test("HbA1c", LabTestCategory.BIOCHEMISTRY, is_active=True)
        create_catalog_test("Inactive Test", LabTestCategory.OTHER, is_active=False)

    def test_authenticated_user_can_list_active_lab_tests(self):
        response = self.client.get("/api/lab-orders/tests/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)

    def test_inactive_lab_tests_not_returned(self):
        response = self.client.get("/api/lab-orders/tests/")
        payload = json.dumps(response.data["data"])
        self.assertNotIn("Inactive Test", payload)

    def test_filter_by_category_works(self):
        response = self.client.get(f"/api/lab-orders/tests/?category={LabTestCategory.HEMATOLOGY}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["name"], "CBC")

    def test_search_by_name_works(self):
        response = self.client.get("/api/lab-orders/tests/?search=hba")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["name"], "HbA1c")


class LabOrderCreationTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.consultation = create_consultation(
            self.patient, self.doctor, ConsultationStatus.ACCEPTED
        )
        self.catalog = create_catalog_test("CBC")

    def _url(self):
        return f"/api/consultations/{self.consultation.id}/lab-orders/"

    def _payload(self):
        return {
            "items": [
                {
                    "test": str(self.catalog.id),
                    "test_name": "CBC",
                    "category": LabTestCategory.HEMATOLOGY,
                    "sample_type": "Blood",
                    "instructions": "Fasting not required",
                }
            ]
        }

    def test_assigned_approved_doctor_can_create_for_accepted_consultation(self):
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_doctor_can_create_for_doctor_responded_consultation(self):
        self.consultation.status = ConsultationStatus.DOCTOR_RESPONDED
        self.consultation.save(update_fields=["status", "updated_at"])
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unassigned_doctor_cannot_create(self):
        response = auth_client(create_doctor("other@example.com")).post(
            self._url(), self._payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unapproved_doctor_cannot_create(self):
        unapproved = create_doctor("unapproved@example.com", approved=False)
        self.consultation.assigned_doctor = unapproved
        self.consultation.save(update_fields=["assigned_doctor", "updated_at"])
        response = auth_client(unapproved).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_create(self):
        response = auth_client(self.patient).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pharmacist_cannot_create(self):
        response = auth_client(create_pharmacist()).post(
            self._url(), self._payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_laboratorian_cannot_create(self):
        response = auth_client(create_laboratorian()).post(
            self._url(), self._payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_create_for_submitted_consultation(self):
        self.consultation.status = ConsultationStatus.SUBMITTED
        self.consultation.save(update_fields=["status", "updated_at"])
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_with_zero_items(self):
        response = auth_client(self.doctor).post(self._url(), {"items": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LabOrderQueryPerformanceTests(TestCase):
    def setUp(self):
        self.patient = create_patient("perf-patient@example.com")
        self.doctor = create_doctor("perf-doctor@example.com")
        self.consultation = create_consultation(
            self.patient,
            self.doctor,
            ConsultationStatus.ACCEPTED,
        )
        self.catalog = create_catalog_test("Perf CBC")
        self.client = APIClient()
        self.client.force_authenticate(self.patient)
        for _ in range(5):
            consultation = create_consultation(
                self.patient,
                self.doctor,
                ConsultationStatus.ACCEPTED,
            )
            create_lab_order_with_items(self.patient, self.doctor, consultation, item_count=3)

    def _url(self):
        return f"/api/consultations/{self.consultation.id}/lab-orders/"

    def _payload(self):
        return {
            "items": [
                {
                    "test": str(self.catalog.id),
                    "test_name": "Perf CBC",
                    "category": LabTestCategory.HEMATOLOGY,
                    "sample_type": "Blood",
                    "instructions": "Fasting not required",
                }
            ]
        }

    def test_patient_lab_order_list_uses_bounded_queries(self):
        with CaptureQueriesContext(connection) as context:
            response = self.client.get("/api/lab-orders/my/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(context), 4)

    def test_lab_order_creates_secure_qr_token(self):
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreater(len(response.data["data"]["qr_token"]), 20)

    def test_lab_order_expires_at_set(self):
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["data"]["expires_at"])

    def test_audit_log_created_on_lab_order_creation(self):
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AuditLog.objects.filter(action="lab_order_created").exists())

    def test_patient_notification_created_without_test_names(self):
        response = auth_client(self.doctor).post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notif = Notification.objects.filter(
            recipient=self.patient, notification_type=NotificationType.LAB_ORDER
        ).latest("created_at")
        self.assertEqual(notif.title, "Lab order issued")
        text = f"{notif.message} {json.dumps(notif.data)}"
        self.assertNotIn("CBC", text)
        self.assertIn("lab_order_id", notif.data)


class PatientSafetyTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.other_patient = create_patient("other@example.com")
        self.doctor = create_doctor()
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(self.patient, self.doctor, self.consultation)

    def test_patient_can_list_own_lab_orders(self):
        response = auth_client(self.patient).get("/api/lab-orders/my/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

    def test_patient_detail_does_not_expose_items_or_test_names_or_instructions(self):
        response = auth_client(self.patient).get(f"/api/lab-orders/my/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        text = json.dumps(data)
        self.assertNotIn("items", data)
        self.assertNotIn("test_name", text)
        self.assertNotIn("instructions", text)
        self.assertNotIn("sample_type", text)

    def test_patient_detail_includes_test_count_and_guidance(self):
        response = auth_client(self.patient).get(f"/api/lab-orders/my/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["test_count"], 2)
        self.assertIn("Show this QR code", response.data["data"]["guidance"])

    def test_other_patient_cannot_view_lab_order(self):
        response = auth_client(self.other_patient).get(f"/api/lab-orders/my/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_scan_qr_endpoint(self):
        response = auth_client(self.patient).post(
            "/api/lab-orders/scan/", {"qr_token": self.lab_order.qr_token}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DoctorVisibilityTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.other_doctor = create_doctor("other_doc@example.com")
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(self.patient, self.doctor, self.consultation)

    def test_ordering_doctor_can_view_full_lab_order(self):
        response = auth_client(self.doctor).get(f"/api/lab-orders/doctor/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_doctor_detail_includes_items_and_completion_records(self):
        response = auth_client(self.doctor).get(f"/api/lab-orders/doctor/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("items", response.data["data"])
        self.assertIn("completion_records", response.data["data"])

    def test_other_doctor_cannot_view_full_lab_order(self):
        response = auth_client(self.other_doctor).get(
            f"/api/lab-orders/doctor/{self.lab_order.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_can_cancel_if_no_items_completed(self):
        response = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/{self.lab_order.id}/cancel/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lab_order.refresh_from_db()
        self.assertEqual(self.lab_order.status, LabOrderStatus.CANCELLED)

    def test_doctor_cannot_cancel_after_any_item_completed(self):
        item = self.lab_order.items.first()
        item.status = LabOrderItemStatus.COMPLETED
        item.completed_at = timezone.now()
        item.save(update_fields=["status", "completed_at", "updated_at"])
        response = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/{self.lab_order.id}/cancel/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancellation_sets_pending_items_cancelled(self):
        response = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/{self.lab_order.id}/cancel/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.lab_order.items.filter(status=LabOrderItemStatus.PENDING).exists())
        self.assertEqual(
            self.lab_order.items.filter(status=LabOrderItemStatus.CANCELLED).count(), 2
        )


class LaboratorianScanTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.lab = create_laboratorian(approved=True)
        self.unapproved_lab = create_laboratorian("badlab@example.com", approved=False)
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(self.patient, self.doctor, self.consultation)

    def _scan(self, user, token=None):
        return auth_client(user).post(
            "/api/lab-orders/scan/",
            {"qr_token": token or self.lab_order.qr_token},
            format="json",
        )

    def test_approved_laboratorian_can_scan_active_qr(self):
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["remaining_items"]), 2)

    def test_unapproved_laboratorian_cannot_scan(self):
        response = self._scan(self.unapproved_lab)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_doctor_pharmacist_cannot_scan(self):
        self.assertEqual(self._scan(self.patient).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._scan(self.doctor).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._scan(self.pharmacist).status_code, status.HTTP_403_FORBIDDEN)

    def test_scan_returns_only_pending_items(self):
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(i["id"] for i in response.data["data"]["remaining_items"]))

    def test_scan_does_not_return_completed_items(self):
        item = self.lab_order.items.first()
        item.status = LabOrderItemStatus.COMPLETED
        item.completed_at = timezone.now()
        item.save(update_fields=["status", "completed_at", "updated_at"])
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["remaining_items"]), 1)

    def test_fully_completed_scan_returns_locked_no_items(self):
        self.lab_order.items.update(
            status=LabOrderItemStatus.COMPLETED, completed_at=timezone.now()
        )
        self.lab_order.update_status_from_items()
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["locked"])
        self.assertEqual(len(response.data["data"]["remaining_items"]), 0)

    def test_expired_scan_returns_locked_no_items(self):
        self.lab_order.expires_at = timezone.now() - timezone.timedelta(days=1)
        self.lab_order.save(update_fields=["expires_at", "updated_at"])
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["locked"])
        self.assertEqual(len(response.data["data"]["remaining_items"]), 0)

    def test_cancelled_scan_returns_locked_no_items(self):
        self.lab_order.status = LabOrderStatus.CANCELLED
        self.lab_order.cancelled_at = timezone.now()
        self.lab_order.save(update_fields=["status", "cancelled_at", "updated_at"])
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["locked"])

    def test_audit_log_created_on_scan(self):
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditLog.objects.filter(action="lab_order_qr_scanned").exists())

    def test_scan_issued_order_empty_completed_items(self):
        """Issued order should have empty completed_items list."""
        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("lab_order", response.data["data"])
        self.assertIn("completed_items", response.data["data"]["lab_order"])
        self.assertEqual(len(response.data["data"]["lab_order"]["completed_items"]), 0)

    def test_scan_partially_completed_returns_completed_items(self):
        """After completing one item, scan should include it in completed_items."""
        item = self.lab_order.items.first()
        item.status = LabOrderItemStatus.COMPLETED
        item.completed_at = timezone.now()
        item.save(update_fields=["status", "completed_at", "updated_at"])
        self.lab_order.update_status_from_items()

        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        completed_items = response.data["data"]["lab_order"]["completed_items"]
        self.assertEqual(len(completed_items), 1)
        self.assertEqual(str(completed_items[0]["id"]), str(item.id))
        self.assertEqual(completed_items[0]["status"], LabOrderItemStatus.COMPLETED)
        self.assertIsNotNone(completed_items[0]["completed_at"])

    def test_scan_fully_completed_returns_all_completed_items(self):
        """Fully completed order should return all items in completed_items."""
        self.lab_order.items.update(
            status=LabOrderItemStatus.COMPLETED, completed_at=timezone.now()
        )
        self.lab_order.update_status_from_items()

        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        completed_items = response.data["data"]["lab_order"]["completed_items"]
        self.assertEqual(len(completed_items), 2)
        self.assertTrue(response.data["data"]["locked"])

    def test_scan_cancelled_items_in_completed_items(self):
        """Cancelled items should be included in completed_items."""
        item = self.lab_order.items.first()
        item.status = LabOrderItemStatus.CANCELLED
        item.cancelled_at = timezone.now()
        item.save(update_fields=["status", "cancelled_at", "updated_at"])
        self.lab_order.update_status_from_items()

        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        completed_items = response.data["data"]["lab_order"]["completed_items"]
        self.assertEqual(len(completed_items), 1)
        self.assertEqual(completed_items[0]["status"], LabOrderItemStatus.CANCELLED)

    def test_completed_items_structure_no_result_exposure(self):
        """completed_items should contain safe metadata, not result values."""
        item = self.lab_order.items.first()
        item.status = LabOrderItemStatus.COMPLETED
        item.completed_at = timezone.now()
        item.save(update_fields=["status", "completed_at", "updated_at"])

        response = self._scan(self.lab)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        completed_item = response.data["data"]["lab_order"]["completed_items"][0]

        # Safe fields should be present
        self.assertIn("id", completed_item)
        self.assertIn("test_name", completed_item)
        self.assertIn("category", completed_item)
        self.assertIn("sample_type", completed_item)
        self.assertIn("instructions", completed_item)
        self.assertIn("status", completed_item)
        self.assertIn("completed_at", completed_item)

        # result_id is OK (points to a result endpoint, not exposing data)
        self.assertIn("result_id", completed_item)


class CompletionTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.lab = create_laboratorian(approved=True)
        self.lab2 = create_laboratorian("lab2@example.com", approved=True)
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=2
        )

    def _complete(self, user, items):
        return auth_client(user).post(
            f"/api/lab-orders/{self.lab_order.id}/complete/",
            {"items": items},
            format="json",
        )

    def test_approved_laboratorian_can_complete_pending_item(self):
        item = self.lab_order.items.first()
        response = self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(item.id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                    "note": "Done",
                }
            ],
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.status, LabOrderItemStatus.COMPLETED)

    def test_completed_item_hidden_from_future_scan(self):
        item = self.lab_order.items.first()
        self._complete(
            self.lab,
            [{"lab_order_item_id": str(item.id), "status": LabCompletionAttemptStatus.COMPLETED}],
        )
        scan = auth_client(self.lab).post(
            "/api/lab-orders/scan/", {"qr_token": self.lab_order.qr_token}, format="json"
        )
        ids = [i["id"] for i in scan.data["data"]["remaining_items"]]
        self.assertNotIn(str(item.id), ids)

    def test_unavailable_attempt_keeps_item_pending_and_visible(self):
        item = self.lab_order.items.first()
        response = self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(item.id),
                    "status": LabCompletionAttemptStatus.UNAVAILABLE,
                    "note": "Not available",
                }
            ],
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.status, LabOrderItemStatus.PENDING)
        self.assertTrue(
            LabCompletionRecord.objects.filter(
                lab_order_item=item, status=LabCompletionAttemptStatus.UNAVAILABLE
            ).exists()
        )

        scan2 = auth_client(self.lab2).post(
            "/api/lab-orders/scan/", {"qr_token": self.lab_order.qr_token}, format="json"
        )
        ids = [i["id"] for i in scan2.data["data"]["remaining_items"]]
        self.assertIn(str(item.id), ids)

    def test_partial_completion_sets_status_partially_completed(self):
        item = self.lab_order.items.first()
        self._complete(
            self.lab,
            [{"lab_order_item_id": str(item.id), "status": LabCompletionAttemptStatus.COMPLETED}],
        )
        self.lab_order.refresh_from_db()
        self.assertEqual(self.lab_order.status, LabOrderStatus.PARTIALLY_COMPLETED)

    def test_all_items_completed_sets_status_fully_completed(self):
        items = list(self.lab_order.items.all())
        response = self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(items[0].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                },
                {
                    "lab_order_item_id": str(items[1].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                },
            ],
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lab_order.refresh_from_db()
        self.assertEqual(self.lab_order.status, LabOrderStatus.FULLY_COMPLETED)
        self.assertIsNotNone(self.lab_order.fully_completed_at)

    def test_cannot_complete_same_item_twice(self):
        item = self.lab_order.items.first()
        self._complete(
            self.lab,
            [{"lab_order_item_id": str(item.id), "status": LabCompletionAttemptStatus.COMPLETED}],
        )
        response = self._complete(
            self.lab,
            [{"lab_order_item_id": str(item.id), "status": LabCompletionAttemptStatus.COMPLETED}],
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_complete_item_from_another_order(self):
        other_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        )
        foreign_item = other_order.items.first()
        response = self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(foreign_item.id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                }
            ],
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_complete_locked_order(self):
        self.lab_order.status = LabOrderStatus.CANCELLED
        self.lab_order.cancelled_at = timezone.now()
        self.lab_order.save(update_fields=["status", "cancelled_at", "updated_at"])
        item = self.lab_order.items.first()
        response = self._complete(
            self.lab,
            [{"lab_order_item_id": str(item.id), "status": LabCompletionAttemptStatus.COMPLETED}],
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_audit_logs_created_for_completed_unavailable_fully_completed(self):
        items = list(self.lab_order.items.all())
        self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(items[0].id),
                    "status": LabCompletionAttemptStatus.UNAVAILABLE,
                },
                {
                    "lab_order_item_id": str(items[1].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                },
            ],
        )
        self.assertTrue(AuditLog.objects.filter(action="lab_order_item_unavailable").exists())
        self.assertTrue(AuditLog.objects.filter(action="lab_order_item_completed").exists())

        self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(items[0].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                }
            ],
        )
        self.assertTrue(AuditLog.objects.filter(action="lab_order_fully_completed").exists())

    def test_doctor_and_patient_notifications_created(self):
        items = list(self.lab_order.items.all())
        self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(items[0].id),
                    "status": LabCompletionAttemptStatus.UNAVAILABLE,
                },
                {
                    "lab_order_item_id": str(items[1].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                },
            ],
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.doctor, title="Lab test completed").exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor, title="Lab test unavailable"
            ).exists()
        )

        self._complete(
            self.lab,
            [
                {
                    "lab_order_item_id": str(items[0].id),
                    "status": LabCompletionAttemptStatus.COMPLETED,
                }
            ],
        )
        patient_notif = Notification.objects.filter(
            recipient=self.patient, title="Lab order fully completed"
        ).latest("created_at")
        self.assertTrue(patient_notif)
        self.assertNotIn("test_name", json.dumps(patient_notif.data))


class RoleAccessTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.lab = create_laboratorian()
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(self.patient, self.doctor, self.consultation)

    def test_laboratorian_cannot_view_doctor_detail(self):
        response = auth_client(self.lab).get(f"/api/lab-orders/doctor/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_view_doctor_detail(self):
        response = auth_client(self.patient).get(f"/api/lab-orders/doctor/{self.lab_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_cannot_access_lab_order_endpoints(self):
        client = auth_client(self.pharmacist)
        self.assertEqual(client.get("/api/lab-orders/my/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            client.post(
                "/api/lab-orders/scan/", {"qr_token": self.lab_order.qr_token}, format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )


class LabResultCreationTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.lab = create_laboratorian(approved=True)
        self.unapproved_lab = create_laboratorian("nolabs@example.com", approved=False)
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        )
        self.item = self.lab_order.items.first()
        auth_client(self.lab).post(
            f"/api/lab-orders/{self.lab_order.id}/complete/",
            {
                "items": [
                    {
                        "lab_order_item_id": str(self.item.id),
                        "status": LabCompletionAttemptStatus.COMPLETED,
                    }
                ]
            },
            format="json",
        )

    def _url(self):
        return f"/api/lab-orders/items/{self.item.id}/results/"

    def test_approved_laboratorian_can_create_result_for_completed_item(self):
        response = auth_client(self.lab).post(
            self._url(),
            {"value_type": LabResultValueType.NUMERIC, "numeric_value": "7.2", "unit": "mmol/L"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_result_for_pending_item(self):
        pending_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        )
        pending_item = pending_order.items.first()
        response = auth_client(self.lab).post(
            f"/api/lab-orders/items/{pending_item.id}/results/",
            {"value_type": LabResultValueType.TEXT, "text_value": "ok"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_duplicate_result_for_same_item(self):
        auth_client(self.lab).post(
            self._url(),
            {"value_type": LabResultValueType.TEXT, "text_value": "first"},
            format="json",
        )
        response = auth_client(self.lab).post(
            self._url(),
            {"value_type": LabResultValueType.TEXT, "text_value": "second"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unapproved_or_wrong_roles_cannot_create_result(self):
        self.assertEqual(
            auth_client(self.unapproved_lab)
            .post(self._url(), {"value_type": "text", "text_value": "x"}, format="json")
            .status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            auth_client(self.patient)
            .post(self._url(), {"value_type": "text", "text_value": "x"}, format="json")
            .status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            auth_client(self.doctor)
            .post(self._url(), {"value_type": "text", "text_value": "x"}, format="json")
            .status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            auth_client(create_pharmacist())
            .post(self._url(), {"value_type": "text", "text_value": "x"}, format="json")
            .status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_value_type_validations(self):
        self.assertEqual(
            auth_client(self.lab)
            .post(self._url(), {"value_type": "numeric"}, format="json")
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            auth_client(self.lab)
            .post(self._url(), {"value_type": "text"}, format="json")
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            auth_client(self.lab)
            .post(self._url(), {"value_type": "blood_group"}, format="json")
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        file_item = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        ).items.first()
        auth_client(self.lab).post(
            f"/api/lab-orders/{file_item.lab_order.id}/complete/",
            {
                "items": [
                    {
                        "lab_order_item_id": str(file_item.id),
                        "status": LabCompletionAttemptStatus.COMPLETED,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(
            auth_client(self.lab)
            .post(
                f"/api/lab-orders/items/{file_item.id}/results/",
                {"value_type": "file_only"},
                format="json",
            )
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        file_upload = SimpleUploadedFile(
            "result.pdf", b"pdfcontent", content_type="application/pdf"
        )
        resp = auth_client(self.lab).post(
            f"/api/lab-orders/items/{file_item.id}/results/",
            {"value_type": "file_only", "result_file": file_upload},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_audit_and_doctor_notification_on_result_creation(self):
        response = auth_client(self.lab).post(
            self._url(),
            {"value_type": LabResultValueType.POSITIVE_NEGATIVE, "text_value": "positive"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AuditLog.objects.filter(action="lab_result_created").exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor, title="Lab result submitted"
            ).exists()
        )


class LabResultVisibilityAndWorkflowTests(TestCase):
    def setUp(self):
        self.patient = create_patient()
        self.other_patient = create_patient("other-patient@example.com")
        self.doctor = create_doctor()
        self.other_doctor = create_doctor("other-doc@example.com")
        self.lab = create_laboratorian(approved=True)
        self.other_lab = create_laboratorian("other-lab@example.com", approved=True)
        self.pharmacist = create_pharmacist()
        self.consultation = create_consultation(self.patient, self.doctor)
        self.lab_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        )
        self.item = self.lab_order.items.first()
        auth_client(self.lab).post(
            f"/api/lab-orders/{self.lab_order.id}/complete/",
            {
                "items": [
                    {
                        "lab_order_item_id": str(self.item.id),
                        "status": LabCompletionAttemptStatus.COMPLETED,
                    }
                ]
            },
            format="json",
        )
        create_resp = auth_client(self.lab).post(
            f"/api/lab-orders/items/{self.item.id}/results/",
            {
                "value_type": LabResultValueType.NUMERIC,
                "numeric_value": "10.5",
                "unit": "g/dL",
                "laboratorian_notes": "internal",
            },
            format="json",
        )
        self.result_id = create_resp.data["data"]["id"]

    def test_patient_cannot_see_unreleased_result(self):
        self.assertEqual(
            auth_client(self.patient).get(f"/api/lab-orders/results/{self.result_id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            auth_client(self.patient).get("/api/lab-results/my/").status_code, status.HTTP_200_OK
        )
        self.assertEqual(len(auth_client(self.patient).get("/api/lab-results/my/").data["data"]), 0)

    def test_ordering_doctor_can_view_full_other_doctor_cannot(self):
        self.assertEqual(
            auth_client(self.doctor)
            .get(f"/api/lab-orders/doctor/results/{self.result_id}/")
            .status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            auth_client(self.other_doctor)
            .get(f"/api/lab-orders/doctor/results/{self.result_id}/")
            .status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_review_and_release_workflow(self):
        review = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{self.result_id}/review/",
            {"doctor_notes": "Reviewed", "release_to_patient": False},
            format="json",
        )
        self.assertEqual(review.status_code, status.HTTP_200_OK)
        result = LabResult.objects.get(id=self.result_id)
        self.assertEqual(result.status, LabResultStatus.REVIEWED)
        self.assertIsNotNone(result.reviewed_at)

        release = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{self.result_id}/release/", {}, format="json"
        )
        self.assertEqual(release.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.status, LabResultStatus.RELEASED)
        self.assertIsNotNone(result.released_at)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.patient, title="Lab result released"
            ).exists()
        )

        patient_detail = auth_client(self.patient).get(f"/api/lab-results/my/{self.result_id}/")
        self.assertEqual(patient_detail.status_code, status.HTTP_200_OK)
        payload = str(patient_detail.data["data"])
        self.assertNotIn("laboratorian_notes", payload)
        self.assertNotIn("doctor_notes", payload)

        self.assertEqual(
            auth_client(self.other_patient)
            .get(f"/api/lab-results/my/{self.result_id}/")
            .status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_correction_flow(self):
        resp = auth_client(self.lab).post(
            f"/api/lab-orders/results/{self.result_id}/correct/",
            {"reason": "Calibration issue", "numeric_value": "11.1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        result = LabResult.objects.get(id=self.result_id)
        self.assertEqual(result.status, LabResultStatus.CORRECTED)
        self.assertTrue(LabResultCorrection.objects.filter(lab_result_id=self.result_id).exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.doctor, title="Lab result corrected"
            ).exists()
        )

        self.assertEqual(
            auth_client(self.other_lab)
            .post(
                f"/api/lab-orders/results/{self.result_id}/correct/",
                {"reason": "x", "numeric_value": "9.9"},
                format="json",
            )
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_link_to_medical_record(self):
        # must review/release first
        self.assertEqual(
            auth_client(self.doctor)
            .post(
                f"/api/lab-orders/doctor/results/{self.result_id}/link-medical-record/",
                {},
                format="json",
            )
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{self.result_id}/review/",
            {"release_to_patient": True},
            format="json",
        )

        link_resp = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{self.result_id}/link-medical-record/",
            {},
            format="json",
        )
        self.assertEqual(link_resp.status_code, status.HTTP_200_OK)
        result = LabResult.objects.get(id=self.result_id)
        self.assertTrue(result.is_linked_to_medical_record)
        self.assertIsNotNone(result.linked_entry)
        entry = MedicalRecordEntry.objects.get(id=result.linked_entry_id)
        self.assertEqual(
            entry.verification_status, MedicalRecordVerificationStatus.LABORATORY_CONFIRMED
        )
        self.assertEqual(entry.source_role, MedicalRecordSourceRole.LABORATORIAN)
        self.assertTrue(
            AuditLog.objects.filter(action="lab_result_linked_to_medical_record").exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.patient, title="Medical record updated"
            ).exists()
        )

        # cannot link twice
        self.assertEqual(
            auth_client(self.doctor)
            .post(
                f"/api/lab-orders/doctor/results/{self.result_id}/link-medical-record/",
                {},
                format="json",
            )
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_blood_group_result_updates_blood_group_record(self):
        bg_order = create_lab_order_with_items(
            self.patient, self.doctor, self.consultation, item_count=1
        )
        bg_item = bg_order.items.first()
        auth_client(self.lab).post(
            f"/api/lab-orders/{bg_order.id}/complete/",
            {
                "items": [
                    {
                        "lab_order_item_id": str(bg_item.id),
                        "status": LabCompletionAttemptStatus.COMPLETED,
                    }
                ]
            },
            format="json",
        )
        create_resp = auth_client(self.lab).post(
            f"/api/lab-orders/items/{bg_item.id}/results/",
            {
                "value_type": LabResultValueType.BLOOD_GROUP,
                "blood_group_value": BloodGroup.O_POSITIVE,
            },
            format="json",
        )
        bg_result_id = create_resp.data["data"]["id"]
        auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{bg_result_id}/review/",
            {"release_to_patient": True},
            format="json",
        )
        link_resp = auth_client(self.doctor).post(
            f"/api/lab-orders/doctor/results/{bg_result_id}/link-medical-record/",
            {},
            format="json",
        )
        self.assertEqual(link_resp.status_code, status.HTTP_200_OK)
        bg_record = BloodGroupRecord.objects.get(medical_record__patient=self.patient)
        self.assertEqual(bg_record.blood_group, BloodGroup.O_POSITIVE)
        self.assertEqual(
            bg_record.verification_status, MedicalRecordVerificationStatus.LABORATORY_CONFIRMED
        )

    def test_role_restrictions_for_result_endpoints(self):
        self.assertEqual(
            auth_client(self.pharmacist)
            .get(f"/api/lab-orders/results/{self.result_id}/")
            .status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            auth_client(self.patient)
            .post(
                f"/api/lab-orders/doctor/results/{self.result_id}/link-medical-record/",
                {},
                format="json",
            )
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )
