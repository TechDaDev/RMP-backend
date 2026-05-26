import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import UserType

from .models import CatalogImportBatch, Drug, DrugAlias

User = get_user_model()


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


class DrugCatalogTests(TestCase):
    def setUp(self):
        self.admin = create_user("admin@example.com", is_staff=True)
        self.doctor = create_user("doctor@example.com", user_type=UserType.DOCTOR)
        self.anon_client = APIClient()

        self.active_drug = Drug.objects.create(
            name="Paracetamol",
            generic_name="Acetaminophen",
            form="Tablet",
            strength="500 mg",
            route="oral",
            is_active=True,
        )
        DrugAlias.objects.create(
            drug=self.active_drug,
            alias="Tylenol",
            alias_type=DrugAlias.AliasType.BRAND,
        )
        self.inactive_drug = Drug.objects.create(
            name="Old Drug",
            generic_name="Legacy",
            is_active=False,
        )

    def test_admin_can_create_drug(self):
        client = auth_client(self.admin)
        payload = {
            "name": "Amoxicillin",
            "generic_name": "Amoxicillin",
            "form": "Capsule",
            "strength": "500 mg",
            "route": "oral",
            "source_name": "manual",
        }

        response = client.post("/api/catalog/drugs/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Drug.objects.filter(name="Amoxicillin", is_active=True).exists())

    def test_authenticated_user_can_search_active_drugs(self):
        client = auth_client(self.doctor)

        response = client.get("/api/catalog/drugs/?search=para")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_names = [item["name"] for item in response.data.get("results", [])]
        self.assertIn("Paracetamol", result_names)

    def test_search_works_by_alias(self):
        client = auth_client(self.doctor)

        response = client.get("/api/catalog/drugs/?search=tylenol")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_names = [item["name"] for item in response.data.get("results", [])]
        self.assertIn("Paracetamol", result_names)

    def test_inactive_drugs_do_not_appear_in_search(self):
        client = auth_client(self.doctor)

        response = client.get("/api/catalog/drugs/?search=old")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_names = [item["name"] for item in response.data.get("results", [])]
        self.assertNotIn("Old Drug", result_names)

    def test_delete_soft_deactivates_drug(self):
        client = auth_client(self.admin)

        response = client.delete(f"/api/catalog/drugs/{self.active_drug.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.active_drug.refresh_from_db()
        self.assertFalse(self.active_drug.is_active)

    def test_anonymous_user_cannot_access_drug_search(self):
        response = self.anon_client.get("/api/catalog/drugs/?search=para")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RxnormImportCommandTests(TestCase):
    def _write_json(self, payload):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.flush()
        tmp.close()
        return tmp.name

    def _sample_payload(self):
        return [
            {
                "input_term": "paracetamol",
                "rxcui": "161",
                "name": "acetaminophen",
                "synonym": "Tylenol",
                "synonyms": [
                    "Acephen",
                    "Tylenol",
                    "acetaminophen 500 MG Oral Tablet",
                ],
                "tty": "IN",
                "score": "9.63",
                "rank": "1",
                "source_endpoint_used": [
                    "approximateTerm",
                    "rxcui/properties",
                    "rxcui/allrelated",
                ],
            },
            {
                "input_term": "amox",
                "rxcui": "723",
                "name": "amoxicillin",
                "synonym": "Amoxil",
                "synonyms": ["Amoxil", "Trimox"],
                "tty": "IN",
                "score": "8.55",
                "rank": "1",
            },
        ]

    def test_import_creates_drugs_from_valid_json(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            self.assertEqual(Drug.objects.count(), 2)
            self.assertTrue(Drug.objects.filter(name__iexact="acetaminophen").exists())
            self.assertTrue(Drug.objects.filter(name__iexact="amoxicillin").exists())
        finally:
            os.unlink(file_path)

    def test_import_creates_aliases_from_input_term_and_synonyms(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            drug = Drug.objects.get(name__iexact="acetaminophen")
            aliases = list(drug.aliases.values_list("alias", flat=True))
            self.assertIn("paracetamol", aliases)
            self.assertIn("Tylenol", aliases)
            self.assertIn("Acephen", aliases)
        finally:
            os.unlink(file_path)

    def test_running_command_twice_does_not_duplicate_drugs(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            call_command("import_rxnorm_simplified", file=file_path)
            self.assertEqual(Drug.objects.count(), 2)
        finally:
            os.unlink(file_path)

    def test_running_command_twice_does_not_duplicate_aliases(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            call_command("import_rxnorm_simplified", file=file_path)
            drug = Drug.objects.get(name__iexact="acetaminophen")
            alias_count = drug.aliases.count()
            unique_alias_count = len(set(drug.aliases.values_list("alias", flat=True)))
            self.assertEqual(alias_count, unique_alias_count)
        finally:
            os.unlink(file_path)

    def test_rows_with_missing_name_are_skipped(self):
        payload = self._sample_payload() + [{"rxcui": "999", "name": "   ", "input_term": "blank"}]
        file_path = self._write_json(payload)
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            self.assertEqual(Drug.objects.count(), 2)
            batch = CatalogImportBatch.objects.latest("started_at")
            self.assertEqual(batch.total_records, 3)
            self.assertEqual(batch.skipped_records, 1)
        finally:
            os.unlink(file_path)

    def test_invalid_file_path_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("import_rxnorm_simplified", file="/tmp/does-not-exist-rxnorm.json")

    def test_import_creates_completed_catalog_batch(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path, source_version="2026.05")
            batch = CatalogImportBatch.objects.latest("started_at")
            self.assertEqual(batch.source_name, "rxnorm")
            self.assertEqual(batch.source_version, "2026.05")
            self.assertEqual(batch.status, CatalogImportBatch.Status.COMPLETED)
            self.assertIsNotNone(batch.finished_at)
        finally:
            os.unlink(file_path)

    def test_imported_drug_is_unverified(self):
        file_path = self._write_json(self._sample_payload())
        try:
            call_command("import_rxnorm_simplified", file=file_path)
            drug = Drug.objects.get(name__iexact="acetaminophen")
            self.assertFalse(drug.is_verified)
        finally:
            os.unlink(file_path)
