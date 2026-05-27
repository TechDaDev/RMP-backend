from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import UserType

from .models import LabCatalogImportBatch, LabTest, LabTestAlias, LabTestClinicalInfo

User = get_user_model()

LIST_URL = "/api/catalog/lab-tests/"


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_user(email, user_type=UserType.DOCTOR, is_staff=False):
    return User.objects.create_user(
        email=email,
        password="StrongPass1!",
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
        is_staff=is_staff,
    )


def make_lab_test(name="Complete Blood Count", short_name="CBC", category="Hematology",
                  sample_type="Blood", is_active=True, is_verified=False):
    return LabTest.objects.create(
        name=name,
        short_name=short_name,
        category=category,
        sample_type=sample_type,
        is_active=is_active,
        is_verified=is_verified,
    )


class LabTestCatalogAPITests(TestCase):
    def setUp(self):
        self.admin = create_user("lab_admin@example.com", is_staff=True)
        self.doctor = create_user("lab_doctor@example.com", user_type=UserType.DOCTOR)
        self.anon_client = APIClient()

        self.cbc = make_lab_test(
            name="Complete Blood Count",
            short_name="CBC",
            category="Hematology",
            sample_type="Blood",
            is_active=True,
        )
        LabTestAlias.objects.create(
            lab_test=self.cbc,
            alias="Full Blood Count",
            alias_type=LabTestAlias.AliasType.SYNONYM,
        )
        LabTestAlias.objects.create(
            lab_test=self.cbc,
            alias="FBC",
            alias_type=LabTestAlias.AliasType.SYNONYM,
        )

        self.inactive = make_lab_test(
            name="Obsolete Panel",
            short_name="OP",
            is_active=False,
        )

        self.unverified = make_lab_test(
            name="TSH",
            short_name=None,
            category="Hormones",
            sample_type="Blood",
            is_verified=False,
        )
        self.verified = make_lab_test(
            name="Creatinine",
            short_name=None,
            category="Kidney Function",
            sample_type="Blood",
            is_verified=True,
        )

    # ---------- 5. Anonymous user cannot access ----------
    def test_anonymous_user_is_blocked(self):
        response = self.anon_client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ---------- 1. Admin can create lab test ----------
    def test_admin_can_create_lab_test(self):
        client = auth_client(self.admin)
        payload = {
            "name": "Lipid Profile",
            "short_name": None,
            "category": "Chemistry",
            "sample_type": "Blood",
            "source_name": "manual",
        }
        response = client.post(LIST_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(LabTest.objects.filter(name="Lipid Profile", is_active=True).exists())

    # ---------- 9. Non-admin cannot create/update/delete ----------
    def test_non_admin_cannot_create(self):
        client = auth_client(self.doctor)
        payload = {"name": "Should Fail", "category": "Chemistry", "sample_type": "Blood"}
        response = client.post(LIST_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_update(self):
        client = auth_client(self.doctor)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.patch(url, {"name": "Modified"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_delete(self):
        client = auth_client(self.doctor)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ---------- 2. Authenticated user can search active lab tests ----------
    def test_authenticated_user_can_list(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)

    def test_search_by_name(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"search": "blood count"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)

    # ---------- 3. Search works by alias ----------
    def test_search_by_alias(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"search": "FBC"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)

    # ---------- 4. Inactive lab tests do not appear ----------
    def test_inactive_lab_test_excluded_from_list(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertNotIn("Obsolete Panel", names)

    def test_inactive_lab_test_excluded_from_search(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"search": "Obsolete"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    # ---------- 6. DELETE soft-deactivates lab test ----------
    def test_delete_soft_deactivates(self):
        client = auth_client(self.admin)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.cbc.refresh_from_db()
        self.assertFalse(self.cbc.is_active)

    # ---------- 7. Detail response includes aliases ----------
    def test_detail_includes_aliases(self):
        client = auth_client(self.doctor)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("aliases", response.data)
        alias_texts = [a["alias"] for a in response.data["aliases"]]
        self.assertIn("Full Blood Count", alias_texts)
        self.assertIn("FBC", alias_texts)

    # ---------- 8. Detail response includes clinical_info if exists ----------
    def test_detail_clinical_info_none_when_absent(self):
        client = auth_client(self.doctor)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["clinical_info"])

    def test_detail_clinical_info_present_when_exists(self):
        LabTestClinicalInfo.objects.create(
            lab_test=self.cbc,
            purpose_summary="Measures blood cell components.",
            review_status=LabTestClinicalInfo.ReviewStatus.DRAFT,
        )
        client = auth_client(self.doctor)
        url = f"{LIST_URL}{self.cbc.id}/"
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["clinical_info"])
        self.assertEqual(
            response.data["clinical_info"]["purpose_summary"],
            "Measures blood cell components.",
        )

    # ---------- 10. Category filter ----------
    def test_category_filter(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"category": "Hematology"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)
        self.assertNotIn("Creatinine", names)

    # ---------- 11. Sample type filter ----------
    def test_sample_type_filter(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"sample_type": "Blood"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)

    # ---------- 12. verified=true filter ----------
    def test_verified_true_filter(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"verified": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Creatinine", names)
        self.assertNotIn("TSH", names)
        self.assertNotIn("Complete Blood Count", names)

    def test_verified_false_filter(self):
        client = auth_client(self.doctor)
        response = client.get(LIST_URL, {"verified": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Complete Blood Count", names)
        self.assertNotIn("Creatinine", names)


class LabTestDisplayNameTests(TestCase):
    def test_display_name_short_and_name_differ(self):
        lt = LabTest(name="Complete Blood Count", short_name="CBC")
        self.assertEqual(lt.display_name, "CBC - Complete Blood Count")

    def test_display_name_short_name_same_as_name(self):
        lt = LabTest(name="CBC", short_name="CBC")
        self.assertEqual(lt.display_name, "CBC")

    def test_display_name_no_short_name(self):
        lt = LabTest(name="Urinalysis")
        self.assertEqual(lt.display_name, "Urinalysis")


class SeedLabTestsCommandTests(TestCase):
    def test_seed_creates_lab_tests(self):
        call_command("seed_lab_tests", verbosity=0)
        self.assertGreater(LabTest.objects.count(), 0)

    def test_seed_creates_aliases(self):
        call_command("seed_lab_tests", verbosity=0)
        self.assertGreater(LabTestAlias.objects.count(), 0)

    def test_seed_is_idempotent(self):
        call_command("seed_lab_tests", verbosity=0)
        first_count = LabTest.objects.count()
        first_alias_count = LabTestAlias.objects.count()
        call_command("seed_lab_tests", verbosity=0)
        self.assertEqual(LabTest.objects.count(), first_count)
        self.assertEqual(LabTestAlias.objects.count(), first_alias_count)

    def test_seeded_tests_are_unverified(self):
        call_command("seed_lab_tests", verbosity=0)
        self.assertEqual(LabTest.objects.filter(is_verified=True).count(), 0)

    def test_seed_creates_completed_import_batch(self):
        call_command("seed_lab_tests", verbosity=0)
        batch = LabCatalogImportBatch.objects.filter(source_name="manual_seed").last()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.status, LabCatalogImportBatch.Status.COMPLETED)
