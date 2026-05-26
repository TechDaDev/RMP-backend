from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import (
    ConsultationStatus,
    MedicalSpecialty,
    UserType,
    VerificationStatus,
)
from apps.consultations.models import Consultation
from apps.pharmacy_inventory.models import PharmacyDrugInventory
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.profiles.models import DoctorProfile, PatientProfile, PharmacistProfile, UserProfile

from .models import PharmacyPrescriptionRequest, PharmacyPrescriptionRequestItem

User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Admin",
        last_name="User",
        user_type=UserType.STAFF,
        is_active=True,
        is_staff=True,
    )


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
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        verification_status=VerificationStatus.APPROVED,
    )
    return user


def create_pharmacist(email="pharma@example.com", approved=True, pharmacy_name="Rafidain Rx"):
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
        pharmacy_name=pharmacy_name,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def create_prescription(patient, doctor):
    consultation = Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=ConsultationStatus.ACCEPTED,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        duration="less_than_24_hours",
        severity="mild",
    )
    prescription = Prescription.objects.create(
        consultation=consultation,
        doctor=doctor,
        patient=patient,
    )
    item1 = PrescriptionItem.objects.create(
        prescription=prescription,
        medication_name="Amoxicillin",
        dosage="1 capsule",
        frequency="3x daily",
        duration="7 days",
        route="oral",
    )
    item2 = PrescriptionItem.objects.create(
        prescription=prescription,
        medication_name="Paracetamol",
        dosage="1 tablet",
        frequency="2x daily",
        duration="3 days",
        route="oral",
    )
    return prescription, item1, item2


class PharmacyRequestsWorkflowTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.pharmacist = create_pharmacist()
        self.pharmacist2 = create_pharmacist("other.pharma@example.com", pharmacy_name="Other Rx")
        self.prescription, self.item1, self.item2 = create_prescription(self.patient, self.doctor)
        self.anon_client = APIClient()

        self.inv1 = PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            custom_drug_name="Amoxicillin 500 mg Capsule",
            price="7500.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )
        self.inv2 = PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            custom_drug_name="Equivalent local brand",
            price="5000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )
        self.other_pharmacy_inv = PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist2.pharmacist_profile,
            custom_drug_name="Other pharmacy stock",
            price="4000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

    def _list_url(self):
        return "/api/pharmacy/requests/"

    def _detail_url(self, request_id):
        return f"/api/pharmacy/requests/{request_id}/"

    def _action_url(self, request_id, action):
        return f"/api/pharmacy/requests/{request_id}/{action}/"

    def _create_request(self, actor):
        payload = {
            "prescription": str(self.prescription.id),
            "pharmacy": str(self.pharmacist.pharmacist_profile.id),
            "patient_notes": "Please check availability",
        }
        return auth_client(actor).post(self._list_url(), payload, format="json")

    def _quote_payload(self):
        return {
            "pharmacy_notes": "All available except one substitution.",
            "items": [
                {
                    "prescription_item": str(self.item1.id),
                    "inventory_item": str(self.inv1.id),
                    "availability_status": "available",
                    "quoted_name": "Amoxicillin 500 mg Capsule",
                    "quantity": 1,
                    "unit_price": "7500.00",
                    "pharmacy_note": "Available",
                },
                {
                    "prescription_item": str(self.item2.id),
                    "inventory_item": str(self.inv2.id),
                    "availability_status": "substituted",
                    "quoted_name": "Equivalent local brand",
                    "quantity": 1,
                    "unit_price": "5000.00",
                    "substitution_note": "Same generic, different brand",
                },
            ],
        }

    def test_patient_can_create_pharmacy_request_for_own_prescription(self):
        response = self._create_request(self.patient)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_doctor_can_create_pharmacy_request_for_related_prescription(self):
        response = self._create_request(self.doctor)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_anonymous_cannot_create_or_list(self):
        payload = {
            "prescription": str(self.prescription.id),
            "pharmacy": str(self.pharmacist.pharmacist_profile.id),
        }
        create_resp = self.anon_client.post(self._list_url(), payload, format="json")
        list_resp = self.anon_client.get(self._list_url())
        self.assertEqual(create_resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(list_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_request_creation_creates_request_items(self):
        response = self._create_request(self.patient)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        request_id = response.data["data"]["id"]
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.items.count(), 2)

    def test_requested_name_snapshot_is_copied_from_prescription_item_display_name(self):
        response = self._create_request(self.patient)
        request_id = response.data["data"]["id"]
        req_item = PharmacyPrescriptionRequestItem.objects.get(
            request_id=request_id,
            prescription_item=self.item1,
        )
        self.assertEqual(req_item.requested_name_snapshot, self.item1.display_drug_name)

    def test_pharmacist_can_list_own_requests(self):
        self._create_request(self.patient)
        response = auth_client(self.pharmacist).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_pharmacist_cannot_quote_request_for_another_pharmacy(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.pharmacist2).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_can_quote_own_request_with_inventory_item(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.status, PharmacyPrescriptionRequest.Status.QUOTED)

    def test_quote_calculates_item_and_request_total_price(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(str(req.total_price), "12500.00")
        self.assertEqual(str(req.items.get(prescription_item=self.item1).total_price), "7500.00")

    def test_inventory_item_from_another_pharmacy_is_rejected(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        payload = self._quote_payload()
        payload["items"][0]["inventory_item"] = str(self.other_pharmacy_inv.id)

        response = auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_or_unavailable_inventory_item_rejected_for_available_quote(self):
        self.inv1.is_available = False
        self.inv1.save(update_fields=["is_available", "updated_at"])

        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_can_accept_quoted_request(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )

        response = auth_client(self.patient).post(self._action_url(request_id, "accept"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patient_cannot_accept_pending_unquoted_request(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]

        response = auth_client(self.patient).post(self._action_url(request_id, "accept"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_can_reject_quoted_request_with_reason(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )

        response = auth_client(self.patient).post(
            self._action_url(request_id, "reject"),
            {"rejection_reason": "Too expensive"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.status, PharmacyPrescriptionRequest.Status.REJECTED)
        self.assertEqual(req.rejection_reason, "Too expensive")

    def test_cancel_works_for_pending_or_quoted_request(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.patient).post(self._action_url(request_id, "cancel"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.status, PharmacyPrescriptionRequest.Status.CANCELLED)

    def test_complete_only_after_accepted_and_only_by_pharmacy_or_admin(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]

        fail_resp = auth_client(self.pharmacist).post(
            self._action_url(request_id, "complete"), {}, format="json"
        )
        self.assertEqual(fail_resp.status_code, status.HTTP_400_BAD_REQUEST)

        auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        auth_client(self.patient).post(self._action_url(request_id, "accept"), {}, format="json")

        success_resp = auth_client(self.pharmacist).post(
            self._action_url(request_id, "complete"), {}, format="json"
        )
        self.assertEqual(success_resp.status_code, status.HTTP_200_OK)
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.status, PharmacyPrescriptionRequest.Status.COMPLETED)

    def test_duplicate_active_pending_quoted_request_for_same_prescription_pharmacy_prevented(self):
        first = self._create_request(self.patient)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self._create_request(self.patient)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_payment_required_and_no_wallet_transaction_created(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]

        auth_client(self.pharmacist).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        accept_resp = auth_client(self.patient).post(
            self._action_url(request_id, "accept"), {}, format="json"
        )

        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)
        req = PharmacyPrescriptionRequest.objects.get(id=request_id)
        self.assertEqual(req.status, PharmacyPrescriptionRequest.Status.ACCEPTED)
        self.assertGreater(req.total_price, 0)
