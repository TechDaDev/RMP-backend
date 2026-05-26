from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import MedicalSpecialty, UserType, VerificationStatus
from apps.lab_catalog.models import LabTest, LabTestAlias
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    UserProfile,
)

from .models import LabTestOffering

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


def create_lab_test(name="Complete Blood Count", short_name="CBC", is_active=True):
    return LabTest.objects.create(
        name=name,
        short_name=short_name,
        category="Hematology",
        sample_type="Blood",
        is_active=is_active,
        is_verified=True,
    )


class LabInventoryApiTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.lab_user = create_laboratorian("lab-user@example.com")
        self.other_lab_user = create_laboratorian(
            "other-lab@example.com", laboratory_name="Other Lab"
        )
        self.doctor = create_doctor()
        self.patient = create_patient()
        self.anon_client = APIClient()

        self.active_test = create_lab_test()
        LabTestAlias.objects.create(
            lab_test=self.active_test,
            alias="FBC",
            alias_type=LabTestAlias.AliasType.SYNONYM,
        )
        self.inactive_test = create_lab_test("Inactive Test", "IT", is_active=False)

    def _list_url(self):
        return "/api/lab/inventory/"

    def _detail_url(self, offering_id):
        return f"/api/lab/inventory/{offering_id}/"

    def _error_details(self, response):
        return response.data.get("error", {}).get("details", response.data)

    def test_admin_can_create_offering_with_catalog_lab_test(self):
        payload = {
            "lab": str(self.lab_user.laboratorian_profile.id),
            "lab_test": str(self.active_test.id),
            "local_name": "CBC",
            "sample_type_override": "Blood",
            "estimated_turnaround_time": "Same day",
            "price": "10000.00",
            "currency": "IQD",
            "is_available": True,
        }

        response = auth_client(self.admin).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            LabTestOffering.objects.filter(
                lab=self.lab_user.laboratorian_profile,
                lab_test=self.active_test,
                is_active=True,
            ).exists()
        )

    def test_lab_user_can_create_offering_for_own_lab(self):
        payload = {
            "lab_test": str(self.active_test.id),
            "price": "12000.00",
            "currency": "IQD",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        offering = LabTestOffering.objects.get(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            is_active=True,
        )
        self.assertEqual(offering.lab_id, self.lab_user.laboratorian_profile.id)

    def test_lab_user_cannot_create_or_update_another_labs_offering(self):
        payload = {
            "lab": str(self.other_lab_user.laboratorian_profile.id),
            "lab_test": str(self.active_test.id),
            "price": "9000.00",
            "is_available": True,
        }

        create_response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_400_BAD_REQUEST)

        offering = LabTestOffering.objects.create(
            lab=self.other_lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="8000.00",
            is_available=True,
        )
        update_response = auth_client(self.lab_user).patch(
            self._detail_url(offering.id), {"price": "9999.00"}, format="json"
        )
        self.assertEqual(update_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_offering_can_be_created_with_custom_test_name_only(self):
        payload = {
            "custom_test_name": "Special local test not in catalog",
            "sample_type_override": "Blood",
            "estimated_turnaround_time": "24 hours",
            "price": "25000.00",
            "currency": "IQD",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        offering = LabTestOffering.objects.get(
            lab=self.lab_user.laboratorian_profile,
            custom_test_name="Special local test not in catalog",
            is_active=True,
        )
        self.assertIsNone(offering.lab_test)

    def test_creating_without_lab_test_or_custom_test_name_fails(self):
        payload = {
            "price": "1000.00",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_lab_test_cannot_be_selected(self):
        payload = {
            "lab_test": str(self.inactive_test.id),
            "price": "11000.00",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lab_test", self._error_details(response))

    def test_search_works_by_catalog_lab_test_name(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
        )

        response = auth_client(self.lab_user).get(f"{self._list_url()}?search=blood")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_search_works_by_lab_test_alias(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
        )

        response = auth_client(self.lab_user).get(f"{self._list_url()}?search=fbc")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_search_works_by_custom_test_name(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            custom_test_name="Local chemistry panel",
            price="17000.00",
            is_available=True,
        )

        response = auth_client(self.lab_user).get(f"{self._list_url()}?search=chemistry")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_available_true_returns_only_available_active_offerings(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
        )
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            custom_test_name="Unavailable test",
            price="4000.00",
            is_available=False,
        )

        response = auth_client(self.lab_user).get(f"{self._list_url()}?available=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["results"][0]["is_available"])

    def test_inactive_offerings_do_not_appear_in_default_list(self):
        active = LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
            is_active=True,
        )
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            custom_test_name="Inactive offering",
            price="8000.00",
            is_available=True,
            is_active=False,
        )

        response = auth_client(self.lab_user).get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(str(active.id), ids)
        self.assertEqual(len(ids), 1)

    def test_delete_soft_deactivates_offering(self):
        offering = LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
        )

        response = auth_client(self.lab_user).delete(self._detail_url(offering.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        offering.refresh_from_db()
        self.assertFalse(offering.is_active)

    def test_anonymous_user_cannot_access(self):
        response = self.anon_client.get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_negative_price_is_rejected(self):
        payload = {
            "lab_test": str(self.active_test.id),
            "price": "-1.00",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price", self._error_details(response))

    def test_duplicate_active_lab_and_lab_test_offering_is_prevented(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
        )

        payload = {
            "lab_test": str(self.active_test.id),
            "price": "10000.00",
            "is_available": True,
        }

        response = auth_client(self.lab_user).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lab_test", self._error_details(response))

    def test_other_authenticated_users_can_read_but_cannot_write(self):
        LabTestOffering.objects.create(
            lab=self.lab_user.laboratorian_profile,
            lab_test=self.active_test,
            price="9000.00",
            is_available=True,
            is_active=True,
        )

        doctor_list_response = auth_client(self.doctor).get(self._list_url())
        self.assertEqual(doctor_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(doctor_list_response.data["count"], 1)

        patient_list_response = auth_client(self.patient).get(self._list_url())
        self.assertEqual(patient_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patient_list_response.data["count"], 1)

        write_payload = {
            "lab_test": str(self.active_test.id),
            "price": "12000.00",
            "is_available": True,
        }
        doctor_write_response = auth_client(self.doctor).post(
            self._list_url(), write_payload, format="json"
        )
        self.assertEqual(doctor_write_response.status_code, status.HTTP_403_FORBIDDEN)
