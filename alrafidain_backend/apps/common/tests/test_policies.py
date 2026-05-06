from types import SimpleNamespace

from django.test import TestCase

from apps.accounts.models import User
from apps.common.choices import (
    ConsultationDuration,
    ConsultationStatus,
    LabResultStatus,
    SeverityLevel,
    UserType,
    VerificationStatus,
)
from apps.common.policies import ClinicalAccessPolicy, PrivacyPolicy, RoleAccessPolicy
from apps.consultations.models import Consultation
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
)


def _create_user(email: str, user_type: str) -> User:
    password_value = email[::-1]
    user = User.objects.create_user(
        email=email,
        password=password_value,
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
    )
    if user_type == UserType.PATIENT:
        PatientProfile.objects.create(user=user)
    elif user_type == UserType.DOCTOR:
        DoctorProfile.objects.create(user=user)
    elif user_type == UserType.PHARMACIST:
        PharmacistProfile.objects.create(user=user)
    elif user_type == UserType.LABORATORIAN:
        LaboratorianProfile.objects.create(user=user)
    return user


class RoleAccessPolicyTests(TestCase):
    def test_verified_role_helpers(self):
        doctor = _create_user("doctor-policy@example.com", UserType.DOCTOR)
        doctor.doctor_profile.verification_status = VerificationStatus.APPROVED
        doctor.doctor_profile.save(update_fields=["verification_status", "updated_at"])

        pharmacist = _create_user("ph-policy@example.com", UserType.PHARMACIST)
        pharmacist.pharmacist_profile.verification_status = VerificationStatus.PENDING
        pharmacist.pharmacist_profile.save(update_fields=["verification_status", "updated_at"])

        laboratorian = _create_user("lab-policy@example.com", UserType.LABORATORIAN)
        laboratorian.laboratorian_profile.verification_status = VerificationStatus.APPROVED
        laboratorian.laboratorian_profile.save(update_fields=["verification_status", "updated_at"])

        self.assertTrue(RoleAccessPolicy.is_verified_doctor(doctor))
        self.assertFalse(RoleAccessPolicy.is_verified_pharmacist(pharmacist))
        self.assertTrue(RoleAccessPolicy.is_verified_laboratorian(laboratorian))


class ClinicalAccessPolicyTests(TestCase):
    def setUp(self):
        self.patient = _create_user("patient-policy@example.com", UserType.PATIENT)
        self.other_patient = _create_user("patient2-policy@example.com", UserType.PATIENT)
        self.doctor = _create_user("doctor-access@example.com", UserType.DOCTOR)
        self.doctor.doctor_profile.verification_status = VerificationStatus.APPROVED
        self.doctor.doctor_profile.save(update_fields=["verification_status", "updated_at"])

    def test_patient_cannot_access_other_patients_consultation(self):
        consultation = SimpleNamespace(
            patient_id=self.patient.id,
            assigned_doctor_id=self.doctor.id,
        )
        self.assertFalse(
            ClinicalAccessPolicy.can_user_access_consultation(self.other_patient, consultation)
        )

    def test_doctor_can_access_patient_only_with_allowed_relationship(self):
        self.assertFalse(ClinicalAccessPolicy.can_doctor_access_patient(self.doctor, self.patient))

        Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            duration=ConsultationDuration.ONE_TO_THREE_DAYS,
            severity=SeverityLevel.MODERATE,
        )

        self.assertTrue(ClinicalAccessPolicy.can_doctor_access_patient(self.doctor, self.patient))
        self.assertFalse(
            ClinicalAccessPolicy.can_doctor_access_patient(self.doctor, self.other_patient)
        )

    def test_patient_can_only_access_released_lab_result(self):
        released = SimpleNamespace(patient_id=self.patient.id, status=LabResultStatus.RELEASED)
        submitted = SimpleNamespace(patient_id=self.patient.id, status=LabResultStatus.SUBMITTED)

        self.assertTrue(ClinicalAccessPolicy.can_user_access_lab_result(self.patient, released))
        self.assertFalse(ClinicalAccessPolicy.can_user_access_lab_result(self.patient, submitted))

    def test_patient_record_access_checks_ownership(self):
        owned_record = SimpleNamespace(patient=self.patient)
        other_record = SimpleNamespace(patient=self.other_patient)

        self.assertTrue(
            ClinicalAccessPolicy.can_user_access_patient_record(self.patient, owned_record)
        )
        self.assertFalse(
            ClinicalAccessPolicy.can_user_access_patient_record(self.patient, other_record)
        )


class PrivacyPolicyTests(TestCase):
    def setUp(self):
        self.patient = _create_user("privacy-patient@example.com", UserType.PATIENT)
        self.other_patient = _create_user("privacy-other@example.com", UserType.PATIENT)

    def test_patient_privacy_guards(self):
        prescription = SimpleNamespace(patient_id=self.patient.id)
        lab_order = SimpleNamespace(patient_id=self.patient.id)
        released = SimpleNamespace(patient_id=self.patient.id, status=LabResultStatus.RELEASED)

        self.assertTrue(
            PrivacyPolicy.can_patient_see_prescription_items(self.patient, prescription)
        )
        self.assertFalse(
            PrivacyPolicy.can_patient_see_prescription_items(self.other_patient, prescription)
        )

        self.assertTrue(PrivacyPolicy.can_patient_see_lab_order_items(self.patient, lab_order))
        self.assertTrue(PrivacyPolicy.can_patient_see_lab_result(self.patient, released))
