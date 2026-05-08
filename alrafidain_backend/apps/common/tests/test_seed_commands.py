"""Tests for seed management commands."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.common.choices import UserType, VerificationStatus
from apps.consultations.models import Symptom, SymptomCategory, SymptomSpecialtyRule
from apps.lab_orders.models import LabTestCatalog
from apps.patient_records.models import PatientMedicalRecord

User = get_user_model()


def run_command(name, **kwargs):
    out = StringIO()
    call_command(name, stdout=out, stderr=StringIO(), **kwargs)
    return out.getvalue()


class SeedSymptomsCommandTests(TestCase):
    def test_runs_without_error(self):
        output = run_command("seed_symptoms")
        self.assertIn("seed_symptoms done", output)

    def test_creates_expected_categories(self):
        run_command("seed_symptoms")
        self.assertTrue(SymptomCategory.objects.filter(name="General / Constitutional").exists())
        self.assertTrue(SymptomCategory.objects.filter(name="Emergency / Red Flags").exists())
        self.assertGreaterEqual(SymptomCategory.objects.count(), 18)

    def test_creates_symptoms(self):
        run_command("seed_symptoms")
        self.assertTrue(Symptom.objects.filter(name="Fever").exists())
        self.assertTrue(Symptom.objects.filter(name="Chest pain").exists())
        self.assertGreaterEqual(Symptom.objects.count(), 80)

    def test_red_flags_are_set(self):
        run_command("seed_symptoms")
        # Chest pain (non-severe) is no longer a red flag; Severe chest pain is.
        red_flags = [
            "Severe chest pain",
            "Severe shortness of breath",
            "Loss of consciousness",
            "Seizure",
            "Severe bleeding",
            "Suicidal thoughts",
        ]
        for name in red_flags:
            self.assertTrue(
                Symptom.objects.filter(name=name, is_red_flag=True).exists(),
                msg=f"{name} should be a red flag",
            )

    def test_specialty_rules_created(self):
        run_command("seed_symptoms")
        self.assertGreaterEqual(SymptomSpecialtyRule.objects.count(), 5)
        self.assertTrue(
            SymptomSpecialtyRule.objects.filter(
                symptom__name="Eye redness", specialty="ophthalmology"
            ).exists()
        )

    def test_idempotent(self):
        run_command("seed_symptoms")
        count_cats = SymptomCategory.objects.count()
        count_syms = Symptom.objects.count()
        count_rules = SymptomSpecialtyRule.objects.count()

        run_command("seed_symptoms")
        self.assertEqual(SymptomCategory.objects.count(), count_cats)
        self.assertEqual(Symptom.objects.count(), count_syms)
        self.assertEqual(SymptomSpecialtyRule.objects.count(), count_rules)


class SeedLabTestsCommandTests(TestCase):
    def test_runs_without_error(self):
        output = run_command("seed_lab_tests")
        self.assertIn("seed_lab_tests done", output)

    def test_creates_expected_tests(self):
        run_command("seed_lab_tests")
        expected = ["CBC", "Blood Group", "HbA1c", "Thyroid Function Test", "Urine Analysis"]
        for name in expected:
            self.assertTrue(
                LabTestCatalog.objects.filter(name=name).exists(), msg=f"Missing lab test: {name}"
            )

    def test_creates_at_least_16_tests(self):
        run_command("seed_lab_tests")
        self.assertGreaterEqual(LabTestCatalog.objects.count(), 16)

    def test_idempotent(self):
        run_command("seed_lab_tests")
        count = LabTestCatalog.objects.count()
        run_command("seed_lab_tests")
        self.assertEqual(LabTestCatalog.objects.count(), count)


class SeedDemoUsersCommandTests(TestCase):
    def test_runs_without_error(self):
        output = run_command("seed_demo_users")
        self.assertIn("seed_demo_users done", output)

    def test_creates_all_four_demo_users(self):
        run_command("seed_demo_users")
        emails = [
            "patient@example.com",
            "doctor@example.com",
            "pharmacist@example.com",
            "laboratorian@example.com",
        ]
        for email in emails:
            self.assertTrue(User.objects.filter(email=email).exists(), msg=f"Missing user: {email}")

    def test_all_demo_users_are_active(self):
        run_command("seed_demo_users")
        for user in User.objects.filter(email__endswith="@example.com"):
            self.assertTrue(user.is_active, msg=f"{user.email} should be active")

    def test_professional_users_are_approved(self):
        run_command("seed_demo_users")
        doctor = User.objects.get(email="doctor@example.com")
        pharmacist = User.objects.get(email="pharmacist@example.com")
        laboratorian = User.objects.get(email="laboratorian@example.com")

        self.assertEqual(doctor.doctor_profile.verification_status, VerificationStatus.APPROVED)
        self.assertEqual(
            pharmacist.pharmacist_profile.verification_status, VerificationStatus.APPROVED
        )
        self.assertEqual(
            laboratorian.laboratorian_profile.verification_status, VerificationStatus.APPROVED
        )

    def test_demo_patient_has_medical_record(self):
        run_command("seed_demo_users")
        patient = User.objects.get(email="patient@example.com")
        self.assertTrue(PatientMedicalRecord.objects.filter(patient=patient).exists())

    def test_demo_users_can_authenticate(self):
        run_command("seed_demo_users")
        from django.contrib.auth import authenticate

        user = authenticate(username="doctor@example.com", password="DemoPass123!")
        self.assertIsNotNone(user)

    def test_idempotent(self):
        run_command("seed_demo_users")
        count = User.objects.count()
        run_command("seed_demo_users")
        self.assertEqual(User.objects.count(), count)

    def test_doctor_has_specialty(self):
        run_command("seed_demo_users")
        doctor = User.objects.get(email="doctor@example.com")
        self.assertTrue(bool(doctor.doctor_profile.specialty))

    def test_user_type_assignments(self):
        run_command("seed_demo_users")
        self.assertEqual(User.objects.get(email="patient@example.com").user_type, UserType.PATIENT)
        self.assertEqual(User.objects.get(email="doctor@example.com").user_type, UserType.DOCTOR)
        self.assertEqual(
            User.objects.get(email="pharmacist@example.com").user_type, UserType.PHARMACIST
        )
        self.assertEqual(
            User.objects.get(email="laboratorian@example.com").user_type, UserType.LABORATORIAN
        )


class SeedAllCommandTests(TestCase):
    def test_runs_without_error(self):
        output = run_command("seed_all")
        self.assertIn("seed_all: complete", output)

    def test_runs_all_sub_commands(self):
        run_command("seed_all")
        self.assertGreaterEqual(SymptomCategory.objects.count(), 13)
        self.assertGreaterEqual(LabTestCatalog.objects.count(), 16)
        self.assertTrue(User.objects.filter(email="patient@example.com").exists())

    def test_idempotent(self):
        run_command("seed_all")
        sym_count = Symptom.objects.count()
        lab_count = LabTestCatalog.objects.count()
        user_count = User.objects.count()

        run_command("seed_all")
        self.assertEqual(Symptom.objects.count(), sym_count)
        self.assertEqual(LabTestCatalog.objects.count(), lab_count)
        self.assertEqual(User.objects.count(), user_count)
