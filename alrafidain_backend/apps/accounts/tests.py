from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.common.choices import UserType
from apps.common.validators import iraqi_phone_validator
from apps.profiles.models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)

from .models import EmailOTP, OTPPurpose

User = get_user_model()

REGISTER_URL = "/api/accounts/register/"
LOGIN_URL = "/api/accounts/login/"
ME_URL = "/api/accounts/me/"
ACTIVATE_URL = "/api/accounts/activate/"
RESEND_OTP_URL = "/api/accounts/resend-activation-otp/"


def _register(client, user_type=UserType.PATIENT, email="test@example.com"):
    return client.post(
        REGISTER_URL,
        {
            "email": email,
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
            "first_name": "Test",
            "last_name": "User",
            "user_type": user_type,
        },
        format="json",
    )


def _activate(client, email="test@example.com"):
    user = User.objects.get(email=email)
    otp = EmailOTP.objects.filter(
        user=user, purpose=OTPPurpose.ACCOUNT_ACTIVATION, is_used=False
    ).first()
    return client.post(ACTIVATE_URL, {"email": email, "code": otp.code}, format="json")


class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_inactive_user(self):
        _register(self.client)
        user = User.objects.get(email="test@example.com")
        self.assertFalse(user.is_active)

    def test_register_creates_user_profile(self):
        _register(self.client)
        user = User.objects.get(email="test@example.com")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_register_patient_creates_patient_profile(self):
        _register(self.client, user_type=UserType.PATIENT)
        user = User.objects.get(email="test@example.com")
        self.assertTrue(PatientProfile.objects.filter(user=user).exists())

    def test_register_doctor_creates_doctor_profile(self):
        _register(self.client, user_type=UserType.DOCTOR, email="doctor@example.com")
        user = User.objects.get(email="doctor@example.com")
        self.assertTrue(DoctorProfile.objects.filter(user=user).exists())

    def test_register_pharmacist_creates_pharmacist_profile(self):
        _register(self.client, user_type=UserType.PHARMACIST, email="pharm@example.com")
        user = User.objects.get(email="pharm@example.com")
        self.assertTrue(PharmacistProfile.objects.filter(user=user).exists())

    def test_register_laboratorian_creates_laboratorian_profile(self):
        _register(self.client, user_type=UserType.LABORATORIAN, email="lab@example.com")
        user = User.objects.get(email="lab@example.com")
        self.assertTrue(LaboratorianProfile.objects.filter(user=user).exists())

    def test_invalid_user_type_fails(self):
        resp = self.client.post(
            REGISTER_URL,
            {
                "email": "x@example.com",
                "password": "StrongPass1!",
                "password_confirm": "StrongPass1!",
                "first_name": "A",
                "last_name": "B",
                "user_type": "alien",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch_fails(self):
        resp = self.client.post(
            REGISTER_URL,
            {
                "email": "x@example.com",
                "password": "StrongPass1!",
                "password_confirm": "WrongPass!",
                "first_name": "A",
                "last_name": "B",
                "user_type": UserType.PATIENT,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _register(self.client)

    def test_login_fails_before_activation(self):
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_activation_otp_activates_user(self):
        _activate(self.client)
        user = User.objects.get(email="test@example.com")
        self.assertTrue(user.is_active)

    def test_login_succeeds_after_activation(self):
        _activate(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data["data"])


class MeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _register(self.client)
        _activate(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.token = resp.data["data"]["access"]

    def test_me_requires_authentication(self):
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_user_data(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["email"], "test@example.com")


class ProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _register(self.client, user_type=UserType.PATIENT)
        _activate(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.token = resp.data["data"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_patient_can_update_user_profile(self):
        resp = self.client.patch(
            "/api/profiles/me/user-profile/", {"district": "Karrada"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["district"], "Karrada")

    def test_patient_cannot_update_doctor_profile(self):
        resp = self.client.patch(
            "/api/profiles/me/doctor/", {"specialty": "Cardiology"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class VerificationStatusDefaultTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_doctor_profile_starts_pending(self):
        _register(self.client, user_type=UserType.DOCTOR, email="doc@example.com")
        user = User.objects.get(email="doc@example.com")
        self.assertEqual(user.doctor_profile.verification_status, "pending")

    def test_pharmacist_profile_starts_pending(self):
        _register(self.client, user_type=UserType.PHARMACIST, email="ph@example.com")
        user = User.objects.get(email="ph@example.com")
        self.assertEqual(user.pharmacist_profile.verification_status, "pending")

    def test_laboratorian_profile_starts_pending(self):
        _register(self.client, user_type=UserType.LABORATORIAN, email="lab2@example.com")
        user = User.objects.get(email="lab2@example.com")
        self.assertEqual(user.laboratorian_profile.verification_status, "pending")


class PhoneValidatorTests(TestCase):
    def test_valid_077(self):
        iraqi_phone_validator("07712345678")

    def test_valid_078(self):
        iraqi_phone_validator("07812345678")

    def test_valid_075(self):
        iraqi_phone_validator("07512345678")

    def test_valid_079(self):
        iraqi_phone_validator("07912345678")

    def test_invalid_prefix(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            iraqi_phone_validator("07112345678")

    def test_invalid_short(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            iraqi_phone_validator("0771234567")

    def test_invalid_letters(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            iraqi_phone_validator("0771234567A")


# ─── Phase 2 tests ────────────────────────────────────────────────────────────


class OTPHardeningTests(TestCase):
    """New OTP invalidates older; expired OTP fails; wrong OTP fails."""

    def setUp(self):
        self.client = APIClient()
        _register(self.client)
        self.user = User.objects.get(email="test@example.com")

    def test_new_otp_invalidates_old_one(self):
        old_otp = EmailOTP.objects.filter(
            user=self.user, purpose=OTPPurpose.ACCOUNT_ACTIVATION, is_used=False
        ).first()
        # Resend — creates a new OTP, marks old as used
        self.client.post(RESEND_OTP_URL, {"email": "test@example.com"}, format="json")
        old_otp.refresh_from_db()
        self.assertTrue(old_otp.is_used)

    def test_wrong_otp_code_fails(self):
        resp = self.client.post(
            ACTIVATE_URL, {"email": "test@example.com", "code": "000000"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_otp_fails(self):
        from datetime import timedelta

        from django.utils import timezone

        otp = EmailOTP.objects.filter(
            user=self.user, purpose=OTPPurpose.ACCOUNT_ACTIVATION, is_used=False
        ).first()
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save()

        resp = self.client.post(
            ACTIVATE_URL, {"email": "test@example.com", "code": otp.code}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_used_otp_cannot_be_reused(self):
        _activate(self.client)
        otp = EmailOTP.objects.filter(
            user=self.user, purpose=OTPPurpose.ACCOUNT_ACTIVATION, is_used=True
        ).first()
        # Re-register a new inactive user to test the code reuse path
        # Actually: directly attempt activation with the used code
        resp = self.client.post(
            ACTIVATE_URL, {"email": "test@example.com", "code": otp.code}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AuditLogTests(TestCase):
    """Registration, activation, login success/fail, profile update create AuditLog entries."""

    def setUp(self):
        self.client = APIClient()

    def test_registration_creates_audit_log(self):
        _register(self.client)
        self.assertTrue(AuditLog.objects.filter(action="user_registered").exists())

    def test_activation_creates_audit_log(self):
        _register(self.client)
        _activate(self.client)
        self.assertTrue(AuditLog.objects.filter(action="account_activated").exists())

    def test_login_success_creates_audit_log(self):
        _register(self.client)
        _activate(self.client)
        self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.assertTrue(AuditLog.objects.filter(action="login_success").exists())

    def test_login_failed_creates_audit_log(self):
        _register(self.client)
        self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "WrongPassword!"}, format="json"
        )
        self.assertTrue(AuditLog.objects.filter(action="login_failed").exists())

    def test_profile_update_creates_audit_log(self):
        _register(self.client)
        _activate(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        token = resp.data["data"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.patch("/api/profiles/me/user-profile/", {"district": "Karrada"}, format="json")
        self.assertTrue(AuditLog.objects.filter(action="user_profile_updated").exists())


class StandardResponseFormatTests(TestCase):
    """Verify all endpoints return {success, message/data} shape."""

    def setUp(self):
        self.client = APIClient()

    def test_register_returns_success_true(self):
        resp = _register(self.client)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        self.assertIn("message", resp.data)

    def test_login_success_returns_data_with_tokens(self):
        _register(self.client)
        _activate(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "StrongPass1!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["success"])
        self.assertIn("access", resp.data["data"])
        self.assertIn("refresh", resp.data["data"])

    def test_login_failure_returns_success_false(self):
        _register(self.client)
        resp = self.client.post(
            LOGIN_URL, {"email": "test@example.com", "password": "Wrong!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(resp.data["success"])
