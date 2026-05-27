from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import ConsultationStatus, MedicalSpecialty, UserType, VerificationStatus
from apps.consultations.models import Consultation
from apps.lab_catalog.models import LabTest
from apps.lab_inventory.models import LabTestOffering
from apps.lab_orders.models import LabOrder, LabOrderItem
from apps.profiles.models import DoctorProfile, LaboratorianProfile, PatientProfile, UserProfile

from .models import LabOrderRequest, LabOrderRequestItem

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


def create_laboratorian(email="lab@example.com", approved=True, laboratory_name="Rafidain Lab"):
    user = User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Lab",
        last_name="User",
        user_type=UserType.LABORATORIAN,
        is_active=True,
    )
    UserProfile.objects.create(user=user)
    LaboratorianProfile.objects.create(
        user=user,
        laboratory_name=laboratory_name,
        verification_status=VerificationStatus.APPROVED if approved else VerificationStatus.PENDING,
    )
    return user


def create_lab_order(patient, doctor):
    consultation = Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=ConsultationStatus.ACCEPTED,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        duration="less_than_24_hours",
        severity="mild",
    )
    lab_order = LabOrder.objects.create(
        consultation=consultation,
        doctor=doctor,
        patient=patient,
    )
    item1 = LabOrderItem.objects.create(
        lab_order=lab_order,
        test_name="CBC - Complete Blood Count",
        category="hematology",
        sample_type="Blood",
        custom_test_name="CBC - Complete Blood Count",
    )
    item2 = LabOrderItem.objects.create(
        lab_order=lab_order,
        test_name="CRP",
        category="immunology",
        sample_type="Blood",
    )
    return lab_order, item1, item2


def create_lab_test(name="Complete Blood Count", short_name="CBC"):
    return LabTest.objects.create(
        name=name,
        short_name=short_name,
        category="Hematology",
        sample_type="Blood",
        is_active=True,
        is_verified=True,
    )


class LabRequestsWorkflowTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.patient = create_patient()
        self.doctor = create_doctor()
        self.lab_user = create_laboratorian()
        self.other_lab_user = create_laboratorian(
            "other.lab@example.com", laboratory_name="Other Lab"
        )
        self.lab_order, self.item1, self.item2 = create_lab_order(self.patient, self.doctor)
        self.anon_client = APIClient()

        self.catalog_test = create_lab_test()
        self.offering1 = LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.catalog_test,
            price="10000.00",
            is_available=True,
            is_active=True,
        )
        self.offering2 = LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            custom_test_name="Equivalent local test",
            price="15000.00",
            is_available=True,
            is_active=True,
        )
        self.other_lab_offering = LabTestOffering.objects.create(
            lab=self.other_lab_user.laboratorian_profile,
            custom_test_name="Other lab offering",
            price="9000.00",
            is_available=True,
            is_active=True,
        )

    def _list_url(self):
        return "/api/lab/requests/"

    def _action_url(self, request_id, action):
        return f"/api/lab/requests/{request_id}/{action}/"

    def _create_request(self, actor):
        payload = {
            "lab_order": str(self.lab_order.id),
            "lab": str(self.lab_user.laboratorian_profile.id),
            "patient_notes": "Please check availability and price.",
        }
        return auth_client(actor).post(self._list_url(), payload, format="json")

    def _quote_payload(self):
        return {
            "lab_notes": "All tests available except one substitution.",
            "items": [
                {
                    "lab_order_item": str(self.item1.id),
                    "offering": str(self.offering1.id),
                    "availability_status": "available",
                    "quoted_name": "CBC - Complete Blood Count",
                    "quantity": 1,
                    "unit_price": "10000.00",
                    "lab_note": "Same day result",
                },
                {
                    "lab_order_item": str(self.item2.id),
                    "offering": str(self.offering2.id),
                    "availability_status": "substituted",
                    "quoted_name": "Equivalent local test",
                    "quantity": 1,
                    "unit_price": "15000.00",
                    "substitution_note": "Equivalent panel offered by this lab",
                },
            ],
        }

    def test_patient_can_create_lab_request_for_own_lab_order(self):
        response = self._create_request(self.patient)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_doctor_can_create_lab_request_for_related_lab_order(self):
        response = self._create_request(self.doctor)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_anonymous_cannot_create_or_list(self):
        payload = {
            "lab_order": str(self.lab_order.id),
            "lab": str(self.lab_user.laboratorian_profile.id),
        }
        create_resp = self.anon_client.post(self._list_url(), payload, format="json")
        list_resp = self.anon_client.get(self._list_url())
        self.assertEqual(create_resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(list_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_request_creation_automatically_creates_request_items_from_lab_order_items(self):
        response = self._create_request(self.patient)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        request_id = response.data["data"]["id"]
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.items.count(), 2)

    def test_requested_name_snapshot_is_copied_from_lab_order_item_display_test_name(self):
        response = self._create_request(self.patient)
        request_id = response.data["data"]["id"]
        req_item = LabOrderRequestItem.objects.get(
            request_id=request_id,
            lab_order_item=self.item1,
        )
        self.assertEqual(req_item.requested_name_snapshot, self.item1.display_test_name)

    def test_laboratorian_can_list_own_requests(self):
        self._create_request(self.patient)
        response = auth_client(self.lab_user).get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_laboratorian_cannot_quote_request_for_another_lab(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.other_lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_laboratorian_can_quote_own_request_with_offering(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.status, LabOrderRequest.Status.QUOTED)

    def test_quote_calculates_item_total_price_and_request_total_price(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(str(req.total_price), "25000.00")
        self.assertEqual(str(req.items.get(lab_order_item=self.item1).total_price), "10000.00")

    def test_offering_from_another_lab_is_rejected(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        payload = self._quote_payload()
        payload["items"][0]["offering"] = str(self.other_lab_offering.id)

        response = auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_or_unavailable_offering_is_rejected_for_available_quote(self):
        self.offering1.is_available = False
        self.offering1.save(update_fields=["is_available", "updated_at"])

        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_can_accept_quoted_request(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        auth_client(self.lab_user).post(
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
        auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )

        response = auth_client(self.patient).post(
            self._action_url(request_id, "reject"),
            {"rejection_reason": "Too expensive"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.status, LabOrderRequest.Status.REJECTED)
        self.assertEqual(req.rejection_reason, "Too expensive")

    def test_cancel_works_for_pending_or_quoted_request(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]
        response = auth_client(self.patient).post(self._action_url(request_id, "cancel"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.status, LabOrderRequest.Status.CANCELLED)

    def test_complete_works_only_after_accepted_and_only_by_lab_or_admin(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]

        fail_resp = auth_client(self.lab_user).post(
            self._action_url(request_id, "complete"), {}, format="json"
        )
        self.assertEqual(fail_resp.status_code, status.HTTP_400_BAD_REQUEST)

        auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        auth_client(self.patient).post(self._action_url(request_id, "accept"), {}, format="json")

        success_resp = auth_client(self.lab_user).post(
            self._action_url(request_id, "complete"), {}, format="json"
        )
        self.assertEqual(success_resp.status_code, status.HTTP_200_OK)
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.status, LabOrderRequest.Status.COMPLETED)

    def test_duplicate_active_pending_quoted_request_for_same_lab_order_lab_is_prevented(self):
        first = self._create_request(self.patient)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self._create_request(self.patient)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_payment_required_and_no_wallet_transaction_created(self):
        create_resp = self._create_request(self.patient)
        request_id = create_resp.data["data"]["id"]

        auth_client(self.lab_user).post(
            self._action_url(request_id, "quote"), self._quote_payload(), format="json"
        )
        accept_resp = auth_client(self.patient).post(
            self._action_url(request_id, "accept"), {}, format="json"
        )

        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)
        req = LabOrderRequest.objects.get(id=request_id)
        self.assertEqual(req.status, LabOrderRequest.Status.ACCEPTED)
        self.assertGreater(req.total_price, 0)
