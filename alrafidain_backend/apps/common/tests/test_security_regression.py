from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.views import (
    ActivateAccountView,
    ConfirmPasswordResetView,
    LoginView,
    RequestPasswordResetView,
    ResendActivationOTPView,
)
from apps.common.choices import (
    ConsultationStatus,
    LabOrderItemStatus,
    LabResultFlag,
    LabResultStatus,
    LabResultValueType,
    LabTestCategory,
    MedicalSpecialty,
    NotificationType,
    UserType,
    VerificationStatus,
)
from apps.common.throttles import (
    LoginRateThrottle,
    OTPRateThrottle,
    PasswordResetRateThrottle,
    QRScanRateThrottle,
)
from apps.consultations.models import Consultation
from apps.lab_orders.models import LabOrder, LabOrderItem, LabResult
from apps.lab_orders.services import release_lab_result_to_patient
from apps.lab_orders.views import LaboratorianLabOrderScanView
from apps.notifications.models import Notification
from apps.prescriptions.views import PharmacistPrescriptionScanView
from apps.profiles.models import DoctorProfile, LaboratorianProfile, PatientProfile, UserProfile
from config.settings import base as base_settings

User = get_user_model()


class ThrottleConfigRegressionTests(TestCase):
    def test_rest_framework_default_throttle_rates_exist(self):
        rates = base_settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        self.assertEqual(rates.get("anon"), "100/hour")
        self.assertEqual(rates.get("user"), "1000/hour")
        self.assertEqual(rates.get("login"), "10/minute")
        self.assertEqual(rates.get("otp"), "5/minute")
        self.assertEqual(rates.get("qr_scan"), "30/minute")
        self.assertEqual(rates.get("password_reset"), "5/minute")

    def test_accounts_views_have_scoped_throttles(self):
        self.assertEqual(LoginView.throttle_classes, [LoginRateThrottle])
        self.assertEqual(ActivateAccountView.throttle_classes, [OTPRateThrottle])
        self.assertEqual(ResendActivationOTPView.throttle_classes, [OTPRateThrottle])
        self.assertEqual(RequestPasswordResetView.throttle_classes, [PasswordResetRateThrottle])
        self.assertEqual(ConfirmPasswordResetView.throttle_classes, [PasswordResetRateThrottle])

    def test_qr_scan_views_have_scoped_throttles(self):
        self.assertEqual(PharmacistPrescriptionScanView.throttle_classes, [QRScanRateThrottle])
        self.assertEqual(LaboratorianLabOrderScanView.throttle_classes, [QRScanRateThrottle])


class OTPResendPrivacyRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_resend_otp_returns_generic_response_for_unknown_email(self):
        response = self.client.post(
            "/api/accounts/resend-activation-otp/",
            {"email": "missing-user@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.get("message"),
            "If the email exists and is inactive, an OTP has been sent.",
        )

    def test_resend_otp_returns_generic_response_for_active_account(self):
        user = User.objects.create_user(
            email="active@example.com",
            password="StrongPass1!",
            first_name="Active",
            last_name="User",
            user_type=UserType.PATIENT,
            is_active=True,
        )
        UserProfile.objects.create(user=user)
        PatientProfile.objects.create(user=user)

        response = self.client.post(
            "/api/accounts/resend-activation-otp/",
            {"email": "active@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.get("message"),
            "If the email exists and is inactive, an OTP has been sent.",
        )


class LabResultNotificationPrivacyRegressionTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            email="patient-sec@example.com",
            password="StrongPass1!",
            first_name="Pat",
            last_name="Ient",
            user_type=UserType.PATIENT,
            is_active=True,
        )
        self.doctor = User.objects.create_user(
            email="doctor-sec@example.com",
            password="StrongPass1!",
            first_name="Doc",
            last_name="Tor",
            user_type=UserType.DOCTOR,
            is_active=True,
        )
        self.lab = User.objects.create_user(
            email="lab-sec@example.com",
            password="StrongPass1!",
            first_name="Lab",
            last_name="Tech",
            user_type=UserType.LABORATORIAN,
            is_active=True,
        )

        UserProfile.objects.create(user=self.patient)
        UserProfile.objects.create(user=self.doctor)
        UserProfile.objects.create(user=self.lab)
        PatientProfile.objects.create(user=self.patient)
        DoctorProfile.objects.create(
            user=self.doctor,
            specialty=MedicalSpecialty.GENERAL_MEDICINE,
            verification_status=VerificationStatus.APPROVED,
        )
        LaboratorianProfile.objects.create(
            user=self.lab, verification_status=VerificationStatus.APPROVED
        )

        self.consultation = Consultation.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            status=ConsultationStatus.ACCEPTED,
            selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
            duration="less_than_24_hours",
            severity="mild",
        )
        self.lab_order = LabOrder.objects.create(
            consultation=self.consultation,
            doctor=self.doctor,
            patient=self.patient,
        )
        self.lab_order_item = LabOrderItem.objects.create(
            lab_order=self.lab_order,
            test_name="CBC",
            category=LabTestCategory.HEMATOLOGY,
            sample_type="Blood",
            instructions="Fasting not required",
            status=LabOrderItemStatus.COMPLETED,
        )
        self.result = LabResult.objects.create(
            lab_order=self.lab_order,
            lab_order_item=self.lab_order_item,
            patient=self.patient,
            doctor=self.doctor,
            laboratorian=self.lab,
            status=LabResultStatus.SUBMITTED,
            value_type=LabResultValueType.NUMERIC,
            numeric_value="9.80",
            unit="g/dL",
            reference_range="8.5-11.0",
            flag=LabResultFlag.NORMAL,
            laboratorian_notes="internal-only note",
            text_value="",
            blood_group_value="",
        )

    def test_release_notification_does_not_expose_result_values(self):
        release_lab_result_to_patient(self.result, self.doctor)

        notification = Notification.objects.filter(
            recipient=self.patient,
            notification_type=NotificationType.LAB_ORDER,
            title="Lab result released",
        ).latest("created_at")

        self.assertIn("lab_result_id", notification.data)
        self.assertIn("lab_order_id", notification.data)
        self.assertIn("lab_order_item_id", notification.data)

        forbidden_keys = {
            "text_value",
            "numeric_value",
            "blood_group_value",
            "reference_range",
            "unit",
            "flag",
            "laboratorian_notes",
            "doctor_notes",
        }
        self.assertTrue(forbidden_keys.isdisjoint(set(notification.data.keys())))
