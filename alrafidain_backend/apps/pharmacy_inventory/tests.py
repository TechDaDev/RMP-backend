from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import MedicalSpecialty, UserType, VerificationStatus
from apps.medical_catalog.models import Drug, DrugAlias
from apps.profiles.models import DoctorProfile, PatientProfile, PharmacistProfile, UserProfile

from .models import PharmacyDrugInventory

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


def create_pharmacist(email="pharma@example.com", approved=True, pharmacy_name="Rafidain Pharmacy"):
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


class PharmacyInventoryApiTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.pharmacist = create_pharmacist()
        self.other_pharmacist = create_pharmacist("other-pharma@example.com", pharmacy_name="Other Rx")
        self.doctor = create_doctor()
        self.patient = create_patient()
        self.anon_client = APIClient()

        self.active_drug = Drug.objects.create(
            name="Amoxicillin",
            generic_name="Amoxicillin",
            brand_name="Amoxil",
            form="Capsule",
            strength="500 mg",
            route="oral",
            rxnorm_rxcui="723",
            is_active=True,
        )
        DrugAlias.objects.create(
            drug=self.active_drug,
            alias="Mox",
            alias_type=DrugAlias.AliasType.SYNONYM,
        )
        self.inactive_drug = Drug.objects.create(name="Inactive Drug", is_active=False)

    def _list_url(self):
        return "/api/pharmacy/inventory/"

    def _detail_url(self, inventory_id):
        return f"/api/pharmacy/inventory/{inventory_id}/"

    def _response_data(self, response):
        return response.data.get("data", response.data)

    def _error_details(self, response):
        return response.data.get("error", {}).get("details", response.data)

    def test_admin_can_create_inventory_item_with_catalog_drug(self):
        payload = {
            "pharmacy": str(self.pharmacist.pharmacist_profile.id),
            "drug": str(self.active_drug.id),
            "brand_name": "Augmentin",
            "form": "Tablet",
            "strength": "625 mg",
            "price": "7500.00",
            "currency": "IQD",
            "stock_status": "in_stock",
            "quantity": 20,
            "is_available": True,
        }

        response = auth_client(self.admin).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            PharmacyDrugInventory.objects.filter(
                pharmacy=self.pharmacist.pharmacist_profile,
                drug=self.active_drug,
                is_active=True,
            ).exists()
        )

    def test_pharmacy_user_can_create_inventory_item_for_own_pharmacy(self):
        payload = {
            "drug": str(self.active_drug.id),
            "price": "5000.00",
            "currency": "IQD",
            "stock_status": "in_stock",
            "quantity": 12,
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = PharmacyDrugInventory.objects.get(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            is_active=True,
        )
        self.assertEqual(item.pharmacy_id, self.pharmacist.pharmacist_profile.id)

    def test_pharmacy_user_cannot_modify_another_pharmacy_inventory(self):
        inventory = PharmacyDrugInventory.objects.create(
            pharmacy=self.other_pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="5000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.pharmacist).patch(
            self._detail_url(inventory.id), {"price": "9000.00"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inventory_item_can_be_created_with_custom_drug_name_only(self):
        payload = {
            "custom_drug_name": "Local syrup not in catalog",
            "brand_name": "Local Brand",
            "form": "Syrup",
            "strength": "100 ml",
            "price": "5000.00",
            "currency": "IQD",
            "stock_status": "in_stock",
            "quantity": 12,
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = PharmacyDrugInventory.objects.get(
            pharmacy=self.pharmacist.pharmacist_profile,
            custom_drug_name="Local syrup not in catalog",
            is_active=True,
        )
        self.assertIsNone(item.drug)
        self.assertEqual(item.custom_drug_name, "Local syrup not in catalog")

    def test_creating_inventory_without_drug_or_custom_name_fails(self):
        payload = {
            "price": "1000.00",
            "stock_status": "in_stock",
            "quantity": 1,
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_catalog_drug_cannot_be_selected(self):
        payload = {
            "drug": str(self.inactive_drug.id),
            "price": "2000.00",
            "stock_status": "in_stock",
            "quantity": 3,
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("drug", self._error_details(response))

    def test_search_works_by_catalog_drug_alias_or_name(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.pharmacist).get(f"{self._list_url()}?search=mox")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_search_works_by_custom_drug_name(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            custom_drug_name="Local cough syrup",
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.pharmacist).get(f"{self._list_url()}?search=cough")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_available_true_returns_only_available_active_items(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            custom_drug_name="Temp Item",
            price="1200.00",
            stock_status=PharmacyDrugInventory.StockStatus.OUT_OF_STOCK,
            is_available=False,
        )

        response = auth_client(self.pharmacist).get(f"{self._list_url()}?available=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["results"][0]["is_available"])

    def test_out_of_stock_or_unavailable_is_not_treated_as_available(self):
        payload = {
            "drug": str(self.active_drug.id),
            "price": "2500.00",
            "stock_status": "out_of_stock",
            "quantity": 0,
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = PharmacyDrugInventory.objects.get(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            is_active=True,
        )
        self.assertFalse(item.is_available)

    def test_delete_soft_deactivates_item(self):
        inventory = PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.pharmacist).delete(self._detail_url(inventory.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        inventory.refresh_from_db()
        self.assertFalse(inventory.is_active)

    def test_anonymous_user_cannot_access_inventory(self):
        response = self.anon_client.get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_price_cannot_be_negative(self):
        payload = {
            "drug": str(self.active_drug.id),
            "price": "-1.00",
            "stock_status": "in_stock",
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price", self._error_details(response))

    def test_duplicate_active_pharmacy_drug_inventory_is_prevented(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        payload = {
            "drug": str(self.active_drug.id),
            "price": "4500.00",
            "stock_status": "in_stock",
            "is_available": True,
        }

        response = auth_client(self.pharmacist).post(self._list_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("drug", self._error_details(response))

    def test_doctor_can_read_only_available_active_inventory(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.doctor).get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_patient_can_read_only_available_active_inventory(self):
        PharmacyDrugInventory.objects.create(
            pharmacy=self.pharmacist.pharmacist_profile,
            drug=self.active_drug,
            price="3000.00",
            stock_status=PharmacyDrugInventory.StockStatus.IN_STOCK,
            is_available=True,
        )

        response = auth_client(self.patient).get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
