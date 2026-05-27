from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.choices import UserType

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
        self.user = create_user(email=unique_email("patient"))
        self.other = create_user(email=unique_email("other"))
        self.admin = create_user(user_type=UserType.STAFF, is_staff=True, email=unique_email("admin"))
        self.wallet = get_or_create_wallet(self.user)
        self.reference_id = uuid4()

        auth_client(self.admin).post(
            "/api/payments/admin/manual-recharge/",
            {"user": str(self.user.id), "amount": "50000.00"},
            format="json",
        )

    def _create_intent(self, actor, amount="25000.00", ref_id=None):
        return auth_client(actor).post(
            "/api/payments/intents/",
            {
                "service_type": PaymentIntent.ServiceType.LAB_REQUEST,
                "reference_id": str(ref_id or self.reference_id),
                "amount": amount,
                "payment_method": PaymentIntent.PaymentMethod.WALLET,
            },
            format="json",
        )

    def test_user_can_create_wallet_payment_intent(self):
        response = self._create_intent(self.user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PaymentIntent.Status.CREATED)

    def test_duplicate_succeeded_payment_for_same_service_reference_blocked(self):
        first = self._create_intent(self.user)
        intent_id = first.data["id"]
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{intent_id}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)

        second = self._create_intent(self.user)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_pay_wallet_intent_if_balance_is_enough(self):
        create_resp = self._create_intent(self.user)
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(pay_resp.data["status"], PaymentIntent.Status.SUCCEEDED)

    def test_wallet_payment_creates_debit_transaction(self):
        create_resp = self._create_intent(self.user)
        auth_client(self.user).post(f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json")
        self.assertTrue(
            WalletTransaction.objects.filter(
                transaction_type=WalletTransaction.TransactionType.PAYMENT,
                direction=WalletTransaction.Direction.DEBIT,
                reference_id=self.reference_id,
            ).exists()
        )

    def test_wallet_payment_updates_cached_balance(self):
        create_resp = self._create_intent(self.user, amount="25000.00")
        auth_client(self.user).post(f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json")
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.cached_balance, Decimal("25000.00"))

    def test_wallet_payment_fails_if_insufficient_balance(self):
        create_resp = self._create_intent(self.user, amount="9999999.00", ref_id=uuid4())
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_pay_another_users_intent(self):
        other_ref = uuid4()
        create_resp = self._create_intent(self.other, amount="1000.00", ref_id=other_ref)
        pay_resp = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(pay_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_paying_same_intent_twice_is_blocked(self):
        create_resp = self._create_intent(self.user, ref_id=uuid4())
        first_pay = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        second_pay = auth_client(self.user).post(
            f"/api/payments/intents/{create_resp.data['id']}/pay-wallet/", {}, format="json"
        )
        self.assertEqual(first_pay.status_code, status.HTTP_200_OK)
        self.assertEqual(second_pay.status_code, status.HTTP_400_BAD_REQUEST)


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
