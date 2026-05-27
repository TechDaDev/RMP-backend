from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import UserType
from apps.common.choices import ConsultationStatus, MedicalSpecialty, VerificationStatus
from apps.consultations.models import Consultation
from apps.lab_orders.models import LabOrder
from apps.lab_requests.models import LabOrderRequest
from apps.pharmacy_requests.models import PharmacyPrescriptionRequest
from apps.prescriptions.models import Prescription
from apps.profiles.models import DoctorProfile, LaboratorianProfile, PharmacistProfile, PatientProfile, UserProfile

from .models import PaymentIntent, PlatformFeeRule, ProviderEarning, Wallet, WalletTransaction
from .services import (
    calculate_platform_fee,
    create_provider_earning,
    create_wallet_transaction,
    get_or_create_wallet,
)

User = get_user_model()


def unique_email(prefix="user"):
    return f"{prefix}-{uuid4().hex}@example.com"


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_user(user_type=UserType.PATIENT, is_staff=False, email=None):
    return User.objects.create_user(
        email=email or unique_email("user"),
        password="StrongPass1!",
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
        is_staff=is_staff,
    )


def create_patient(email=None):
    user = create_user(user_type=UserType.PATIENT, email=email or unique_email("patient"))
    UserProfile.objects.create(user=user)
    PatientProfile.objects.create(user=user)
    return user


def create_doctor(email=None):
    user = create_user(user_type=UserType.DOCTOR, email=email or unique_email("doctor"))
    UserProfile.objects.create(user=user)
    DoctorProfile.objects.create(
        user=user,
        specialty=MedicalSpecialty.GENERAL_MEDICINE,
        consultation_fee=Decimal("18000.00"),
        consultation_currency="IQD",
        verification_status=VerificationStatus.APPROVED,
    )
    return user


def create_laboratorian(email=None):
    user = create_user(user_type=UserType.LABORATORIAN, email=email or unique_email("lab"))
    UserProfile.objects.create(user=user)
    profile = LaboratorianProfile.objects.create(
        user=user,
        laboratory_name="Resolver Lab",
        verification_status=VerificationStatus.APPROVED,
    )
    return user, profile


def create_pharmacist(email=None):
    user = create_user(user_type=UserType.PHARMACIST, email=email or unique_email("pharmacy"))
    UserProfile.objects.create(user=user)
    profile = PharmacistProfile.objects.create(
        user=user,
        pharmacy_name="Resolver Pharmacy",
        verification_status=VerificationStatus.APPROVED,
    )
    return user, profile


def create_consultation(patient, doctor, *, status=ConsultationStatus.ACCEPTED, consultation_fee=None):
    consultation = Consultation.objects.create(
        patient=patient,
        assigned_doctor=doctor,
        status=status,
        selected_specialty=MedicalSpecialty.GENERAL_MEDICINE,
        duration="less_than_24_hours",
        severity="mild",
    )
    if consultation_fee is not None:
        consultation.consultation_fee = Decimal(consultation_fee)
        consultation.consultation_currency = "IQD"
        consultation.fee_snapshot_at = timezone.now()
        consultation.save(update_fields=["consultation_fee", "consultation_currency", "fee_snapshot_at", "updated_at"])
    return consultation


def create_lab_request(patient, doctor, lab_profile, total_price="25000.00"):
    consultation = create_consultation(patient, doctor)
    lab_order = LabOrder.objects.create(consultation=consultation, doctor=doctor, patient=patient)
    return LabOrderRequest.objects.create(
        lab_order=lab_order,
        patient=patient,
        lab=lab_profile,
        requested_by=patient,
        status=LabOrderRequest.Status.ACCEPTED,
        total_price=Decimal(total_price),
        currency="IQD",
    )


def create_pharmacy_request(patient, doctor, pharmacy_profile, total_price="16000.00"):
    consultation = create_consultation(patient, doctor)
    prescription = Prescription.objects.create(consultation=consultation, doctor=doctor, patient=patient)
    return PharmacyPrescriptionRequest.objects.create(
        prescription=prescription,
        patient=patient,
        pharmacy=pharmacy_profile,
        requested_by=patient,
        status=PharmacyPrescriptionRequest.Status.ACCEPTED,
        total_price=Decimal(total_price),
        currency="IQD",
    )


class WalletTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))
        self.anon = APIClient()

    def test_wallet_is_created_for_new_user(self):
        self.assertTrue(Wallet.objects.filter(user=self.user).exists())

    def test_authenticated_user_can_retrieve_own_wallet(self):
        response = auth_client(self.user).get("/api/payments/wallet/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["user"]), str(self.user.id))

    def test_anonymous_user_cannot_access_wallet(self):
        response = self.anon.get("/api/payments/wallet/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wallet_balance_starts_at_zero(self):
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.cached_balance, Decimal("0.00"))


class ManualRechargeTests(TestCase):
    def setUp(self):
        self.user = create_user(email=unique_email("patient"))
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))
        self.other = create_user(email=unique_email("other"))

    def test_admin_can_manually_recharge_a_user_wallet(self):
        payload = {
            "user": str(self.user.id),
            "amount": "50000.00",
            "description": "Manual test recharge",
        }
        response = auth_client(self.admin).post("/api/payments/admin/manual-recharge/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data["wallet"]["user"]), str(self.user.id))

    def test_non_admin_cannot_manually_recharge(self):
        payload = {
            "user": str(self.user.id),
            "amount": "50000.00",
            "description": "Manual test recharge",
        }
        response = auth_client(self.user).post("/api/payments/admin/manual-recharge/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_negative_zero_recharge_rejected(self):
        zero_response = auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "0.00"},
            format="json",
        )
        neg_response = auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "-1.00"},
            format="json",
        )
        self.assertEqual(zero_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(neg_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recharge_creates_confirmed_credit_wallet_transaction(self):
        response = auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "50000.00"},
            format="json",
        )
        tx = WalletTransaction.objects.get(id=response.data["transaction"]["id"])
        self.assertEqual(tx.status, WalletTransaction.Status.CONFIRMED)
        self.assertEqual(tx.direction, WalletTransaction.Direction.CREDIT)
        self.assertEqual(tx.transaction_type, WalletTransaction.TransactionType.MANUAL_RECHARGE)

    def test_recharge_updates_cached_balance(self):
        auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "50000.00"},
            format="json",
        )
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.cached_balance, Decimal("50000.00"))

    def test_idempotency_prevents_duplicate_transaction_if_same_key_is_used(self):
        key = f"manual-recharge-{uuid4().hex}"
        payload = {
            "user": str(self.user.id),
            "amount": "50000.00",
            "description": "idempotent",
            "idempotency_key": key,
        }
        client = auth_client(self.admin)
        first = client.post("/api/payments/admin/manual-recharge/", payload, format="json")
        second = client.post("/api/payments/admin/manual-recharge/", payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["transaction"]["id"], second.data["transaction"]["id"])
        self.assertEqual(WalletTransaction.objects.filter(idempotency_key=key).count(), 1)


class TransactionVisibilityTests(TestCase):
    def setUp(self):
        self.user_a = create_user(email=unique_email("a"))
        self.user_b = create_user(email=unique_email("b"))
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))

        self.wallet_a = get_or_create_wallet(self.user_a)
        self.wallet_b = get_or_create_wallet(self.user_b)

        create_wallet_transaction(
            wallet=self.wallet_a,
            transaction_type=WalletTransaction.TransactionType.MANUAL_RECHARGE,
            direction=WalletTransaction.Direction.CREDIT,
            amount=Decimal("1000.00"),
            status=WalletTransaction.Status.CONFIRMED,
            idempotency_key=f"tx-a-{uuid4().hex}",
            created_by=self.admin,
        )
        create_wallet_transaction(
            wallet=self.wallet_b,
            transaction_type=WalletTransaction.TransactionType.MANUAL_RECHARGE,
            direction=WalletTransaction.Direction.CREDIT,
            amount=Decimal("2000.00"),
            status=WalletTransaction.Status.CONFIRMED,
            idempotency_key=f"tx-b-{uuid4().hex}",
            created_by=self.admin,
        )

    def test_user_sees_only_own_transactions(self):
        response = auth_client(self.user_a).get("/api/payments/wallet/transactions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(str(response.data["results"][0]["wallet"]), str(self.wallet_a.id))

    def test_admin_can_see_transactions(self):
        response = auth_client(self.admin).get("/api/payments/wallet/transactions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)


class PaymentIntentTests(TestCase):
    def setUp(self):
        self.user = create_patient(email=unique_email("patient"))
        self.other = create_patient(email=unique_email("other"))
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))
        self.wallet = get_or_create_wallet(self.user)

        auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "50000.00"},
            format="json",
        )

    def _create_wallet_recharge_intent(self, actor, amount="25000.00"):
        return auth_client(actor).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.WALLET_RECHARGE,
                "amount": amount,
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )

    def test_user_can_create_wallet_recharge_intent(self):
        response = self._create_wallet_recharge_intent(self.user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PaymentIntent.Status.CREATED)

    def test_user_can_pay_wallet_intent_if_balance_is_enough(self):
        create_resp = self._create_wallet_recharge_intent(self.user)
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(pay_resp.data["status"], PaymentIntent.Status.SUCCEEDED)

    def test_wallet_payment_creates_debit_transaction(self):
        create_resp = self._create_wallet_recharge_intent(self.user)
        auth_client(self.user).post(f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json")
        self.assertTrue(
            WalletTransaction.objects.filter(
                transaction_type=WalletTransaction.TransactionType.PAYMENT,
                direction=WalletTransaction.Direction.DEBIT,
                reference_type=PaymentIntent.ServiceType.WALLET_RECHARGE,
            ).exists()
        )

    def test_wallet_payment_updates_cached_balance(self):
        create_resp = self._create_wallet_recharge_intent(self.user, amount="25000.00")
        auth_client(self.user).post(f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json")
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.cached_balance, Decimal("25000.00"))

    def test_wallet_payment_fails_if_insufficient_balance(self):
        create_resp = self._create_wallet_recharge_intent(self.user, amount="9999999.00")
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_pay_another_users_intent(self):
        create_resp = self._create_wallet_recharge_intent(self.other, amount="1000.00")
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_paying_same_intent_twice_is_blocked(self):
        create_resp = self._create_wallet_recharge_intent(self.user)
        first_pay = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        second_pay = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(first_pay.status_code, status.HTTP_200_OK)
        self.assertEqual(second_pay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wallet_recharge_intent_requires_amount(self):
        response = auth_client(self.user).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.WALLET_RECHARGE,
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ServicePaymentResolutionTests(TestCase):
    def setUp(self):
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))
        self.patient = create_patient(email=unique_email("patient"))
        self.other_patient = create_patient(email=unique_email("other-patient"))
        self.doctor = create_doctor(email=unique_email("doctor"))
        self.lab_user, self.lab_profile = create_laboratorian(email=unique_email("lab"))
        self.pharmacy_user, self.pharmacy_profile = create_pharmacist(email=unique_email("pharmacy"))
        self.consultation = create_consultation(
            self.patient,
            self.doctor,
            status=ConsultationStatus.ACCEPTED,
            consultation_fee="18000.00",
        )

        self.lab_request = create_lab_request(self.patient, self.doctor, self.lab_profile, total_price="25000.00")
        self.pharmacy_request = create_pharmacy_request(
            self.patient,
            self.doctor,
            self.pharmacy_profile,
            total_price="16000.00",
        )

        auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.patient.id), "amount": "50000.00"},
            format="json",
        )

    def test_lab_intent_rejects_client_amount(self):
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "amount": "1.00",
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lab_intent_without_amount_uses_authoritative_total(self):
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount"]), self.lab_request.total_price)
        self.assertEqual(
            str(response.data["metadata"]["provider_user_id"]),
            str(self.lab_user.id),
        )
        self.assertEqual(response.data["metadata"]["provider_type"], ProviderEarning.ProviderType.LAB)

    def test_pharmacy_intent_without_amount_uses_authoritative_total(self):
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.PHARMACY_REQUEST,
                "reference_id": str(self.pharmacy_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount"]), self.pharmacy_request.total_price)
        self.assertEqual(response.data["metadata"]["provider_type"], ProviderEarning.ProviderType.PHARMACY)

    def test_non_owner_patient_cannot_create_service_payment_intent(self):
        response = auth_client(self.other_patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lab_request_must_be_accepted_for_payment(self):
        self.lab_request.status = LabOrderRequest.Status.QUOTED
        self.lab_request.save(update_fields=["status", "updated_at"])

        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consultation_payment_returns_not_configured(self):
        consultation = create_consultation(
            self.patient,
            self.doctor,
            status=ConsultationStatus.ACCEPTED,
            consultation_fee=None,
        )
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not configured", str(response.data["detail"]).lower())

    def test_consultation_intent_without_amount_uses_snapshot_fee(self):
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("18000.00"))
        self.assertEqual(response.data["metadata"]["resolved_amount_source"], "consultation.consultation_fee")
        self.assertEqual(response.data["metadata"]["provider_type"], ProviderEarning.ProviderType.DOCTOR)

    def test_consultation_intent_rejects_client_amount(self):
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "amount": "10.00",
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_owner_patient_cannot_create_consultation_payment_intent(self):
        response = auth_client(self.other_patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consultation_payment_fails_for_non_payable_status(self):
        non_payable = create_consultation(
            self.patient,
            self.doctor,
            status=ConsultationStatus.SUBMITTED,
            consultation_fee="18000.00",
        )
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(non_payable.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accepted", str(response.data["detail"]).lower())

    def test_consultation_payment_fails_if_fee_zero(self):
        consultation = create_consultation(
            self.patient,
            self.doctor,
            status=ConsultationStatus.ACCEPTED,
            consultation_fee="0.00",
        )
        response = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not configured", str(response.data["detail"]).lower())

    def test_consultation_wallet_payment_creates_debit_and_doctor_earning(self):
        PlatformFeeRule.objects.create(
            service_type=PlatformFeeRule.ServiceType.CONSULTATION,
            fee_type=PlatformFeeRule.FeeType.PERCENTAGE,
            value=Decimal("10.00"),
            is_active=True,
        )
        create_resp = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        pay_resp = auth_client(self.patient).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)

        self.assertTrue(
            WalletTransaction.objects.filter(
                transaction_type=WalletTransaction.TransactionType.PAYMENT,
                direction=WalletTransaction.Direction.DEBIT,
                reference_type=PaymentIntent.ServiceType.CONSULTATION,
                reference_id=self.consultation.id,
            ).exists()
        )

        earning = ProviderEarning.objects.get(
            service_type=PaymentIntent.ServiceType.CONSULTATION,
            reference_id=self.consultation.id,
            provider_user=self.doctor,
        )
        self.assertEqual(earning.provider_type, ProviderEarning.ProviderType.DOCTOR)
        self.assertEqual(earning.gross_amount, Decimal("18000.00"))
        self.assertEqual(earning.platform_fee_amount, Decimal("1800.00"))
        self.assertEqual(earning.net_amount, Decimal("16200.00"))

    def test_duplicate_succeeded_payment_for_same_consultation_blocked(self):
        create_resp = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        pay_resp = auth_client(self.patient).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)

        duplicate = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.CONSULTATION,
                "reference_id": str(self.consultation.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_succeeded_payment_for_same_service_reference_blocked(self):
        create_resp = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        pay_resp = auth_client(self.patient).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)

        duplicate = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successful_service_wallet_payment_creates_provider_earning(self):
        create_resp = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(self.lab_request.id),
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        pay_resp = auth_client(self.patient).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ProviderEarning.objects.filter(
                service_type=PaymentIntent.ServiceType.LAB_REQUEST,
                reference_id=self.lab_request.id,
                provider_user=self.lab_user,
            ).exists()
        )

    def test_wallet_recharge_payment_does_not_create_provider_earning(self):
        create_resp = auth_client(self.patient).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.WALLET_RECHARGE,
                "amount": "1000.00",
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        pay_resp = auth_client(self.patient).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(ProviderEarning.objects.count(), 0)


class PlatformFeeTests(TestCase):
    def test_platform_fee_rule_validates_percentage_between_zero_and_hundred(self):
        rule = PlatformFeeRule(
            service_type=PlatformFeeRule.ServiceType.CONSULTATION,
            fee_type=PlatformFeeRule.FeeType.PERCENTAGE,
            value=Decimal("150.00"),
        )
        with self.assertRaises(ValidationError):
            rule.clean()

    def test_calculate_platform_fee_works_for_percentage(self):
        PlatformFeeRule.objects.create(
            service_type=PlatformFeeRule.ServiceType.CONSULTATION,
            fee_type=PlatformFeeRule.FeeType.PERCENTAGE,
            value=Decimal("15.00"),
            is_active=True,
        )
        fee = calculate_platform_fee(PlatformFeeRule.ServiceType.CONSULTATION, Decimal("10000.00"))
        self.assertEqual(fee, Decimal("1500.00"))

    def test_calculate_platform_fee_works_for_fixed(self):
        PlatformFeeRule.objects.create(
            service_type=PlatformFeeRule.ServiceType.LAB_REQUEST,
            fee_type=PlatformFeeRule.FeeType.FIXED,
            value=Decimal("1000.00"),
            is_active=True,
        )
        fee = calculate_platform_fee(PlatformFeeRule.ServiceType.LAB_REQUEST, Decimal("25000.00"))
        self.assertEqual(fee, Decimal("1000.00"))


class ProviderEarningTests(TestCase):
    def setUp(self):
        self.user = create_user(email=unique_email("patient"))
        self.provider = create_user(user_type=UserType.DOCTOR, email=unique_email("doctor"))
        self.wallet = get_or_create_wallet(self.user)

        PlatformFeeRule.objects.create(
            service_type=PlatformFeeRule.ServiceType.CONSULTATION,
            fee_type=PlatformFeeRule.FeeType.PERCENTAGE,
            value=Decimal("15.00"),
            is_active=True,
        )

        self.intent = PaymentIntent.objects.create(
            user=self.user,
            wallet=self.wallet,
            service_type=PaymentIntent.ServiceType.CONSULTATION,
            reference_id=uuid4(),
            amount=Decimal("20000.00"),
            currency="IQD",
            status=PaymentIntent.Status.SUCCEEDED,
            payment_method=PaymentIntent.PaymentMethod.WALLET,
            idempotency_key=f"intent-{uuid4().hex}",
        )

    def test_create_provider_earning_calculates_gross_fee_and_net(self):
        earning = create_provider_earning(
            payment_intent=self.intent,
            provider_user=self.provider,
            provider_type=ProviderEarning.ProviderType.DOCTOR,
        )
        self.assertEqual(earning.gross_amount, Decimal("20000.00"))
        self.assertEqual(earning.platform_fee_amount, Decimal("3000.00"))
        self.assertEqual(earning.net_amount, Decimal("17000.00"))

    def test_duplicate_earning_for_same_service_object_is_prevented(self):
        first = create_provider_earning(
            payment_intent=self.intent,
            provider_user=self.provider,
            provider_type=ProviderEarning.ProviderType.DOCTOR,
        )
        second = create_provider_earning(
            payment_intent=self.intent,
            provider_user=self.provider,
            provider_type=ProviderEarning.ProviderType.DOCTOR,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            ProviderEarning.objects.filter(
                service_type=self.intent.service_type,
                reference_id=self.intent.reference_id,
            ).count(),
            1,
        )
