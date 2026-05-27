from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    PaymentIntent,
    PlatformFeeRule,
    ProviderEarning,
    Wallet,
    WalletTransaction,
    confirmed_wallet_balance,
)


def get_or_create_wallet(user) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(
        user=user,
        defaults={"currency": "IQD", "cached_balance": Decimal("0.00"), "status": Wallet.Status.ACTIVE},
    )
    return wallet


def recalculate_wallet_balance(wallet: Wallet) -> Decimal:
    balance = confirmed_wallet_balance(wallet)
    wallet.cached_balance = balance
    wallet.save(update_fields=["cached_balance", "updated_at"])
    return balance


def create_wallet_transaction(
    *,
    wallet: Wallet,
    transaction_type: str,
    direction: str,
    amount: Decimal,
    currency: str = "IQD",
    status: str = WalletTransaction.Status.PENDING,
    reference_type: str | None = None,
    reference_id=None,
    description: str = "",
    idempotency_key: str,
    metadata: dict | None = None,
    created_by=None,
):
    if amount <= 0:
        raise ValueError("Amount must be positive.")

    if status == WalletTransaction.Status.CONFIRMED and direction == WalletTransaction.Direction.DEBIT:
        current_balance = confirmed_wallet_balance(wallet)
        if current_balance < amount:
            raise ValueError("Insufficient wallet balance.")

    payload = {
        "wallet": wallet,
        "transaction_type": transaction_type,
        "direction": direction,
        "amount": amount,
        "currency": currency,
        "status": status,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "description": description,
        "idempotency_key": idempotency_key,
        "metadata": metadata or {},
        "created_by": created_by,
    }

    try:
        tx = WalletTransaction.objects.create(**payload)
    except IntegrityError:
        tx = WalletTransaction.objects.get(idempotency_key=idempotency_key)

    if tx.status == WalletTransaction.Status.CONFIRMED:
        recalculate_wallet_balance(tx.wallet)

    return tx


def confirm_wallet_transaction(transaction_obj: WalletTransaction) -> WalletTransaction:
    if transaction_obj.status == WalletTransaction.Status.CONFIRMED:
        return transaction_obj

    with transaction.atomic():
        tx = WalletTransaction.objects.select_for_update().get(id=transaction_obj.id)
        if tx.status == WalletTransaction.Status.CONFIRMED:
            return tx

        wallet = Wallet.objects.select_for_update().get(id=tx.wallet_id)
        if tx.direction == WalletTransaction.Direction.DEBIT:
            current_balance = confirmed_wallet_balance(wallet)
            if current_balance < tx.amount:
                raise ValueError("Insufficient wallet balance.")

        tx.status = WalletTransaction.Status.CONFIRMED
        tx.confirmed_at = timezone.now()
        tx.save(update_fields=["status", "confirmed_at", "updated_at"])
        recalculate_wallet_balance(wallet)
        return tx


def create_manual_recharge(
    wallet: Wallet,
    amount: Decimal,
    created_by,
    description: str = "",
    idempotency_key: str | None = None,
):
    if amount <= 0:
        raise ValueError("Amount must be positive.")

    idempotency_key = idempotency_key or f"manual_recharge:{wallet.id}:{amount}:{uuid4().hex}"
    tx = create_wallet_transaction(
        wallet=wallet,
        transaction_type=WalletTransaction.TransactionType.MANUAL_RECHARGE,
        direction=WalletTransaction.Direction.CREDIT,
        amount=amount,
        currency=wallet.currency,
        status=WalletTransaction.Status.CONFIRMED,
        reference_type="admin_adjustment",
        description=description or "Manual recharge",
        idempotency_key=idempotency_key,
        metadata={"source": "admin_manual_recharge"},
        created_by=created_by,
    )
    return tx


def create_payment_intent(
    *,
    user,
    service_type: str,
    reference_id,
    amount: Decimal,
    payment_method: str = PaymentIntent.PaymentMethod.WALLET,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
) -> PaymentIntent:
    if amount <= 0:
        raise ValueError("Amount must be positive.")

    if payment_method not in {
        PaymentIntent.PaymentMethod.WALLET,
        PaymentIntent.PaymentMethod.MANUAL,
    }:
        raise ValueError("Only wallet/manual payment methods are allowed in this phase.")

    if reference_id and PaymentIntent.objects.filter(
        service_type=service_type,
        reference_id=reference_id,
        status=PaymentIntent.Status.SUCCEEDED,
    ).exists():
        raise ValueError("This service object has already been paid.")

    wallet = get_or_create_wallet(user)
    return PaymentIntent.objects.create(
        user=user,
        wallet=wallet,
        service_type=service_type,
        reference_id=reference_id,
        amount=amount,
        currency=wallet.currency,
        status=PaymentIntent.Status.CREATED,
        payment_method=payment_method,
        provider="manual_admin" if payment_method == PaymentIntent.PaymentMethod.MANUAL else None,
        idempotency_key=idempotency_key or f"intent:{service_type}:{reference_id or 'none'}:{user.id}:{uuid4().hex}",
        metadata=metadata or {},
    )


def pay_with_wallet(payment_intent: PaymentIntent) -> PaymentIntent:
    with transaction.atomic():
        intent = PaymentIntent.objects.select_for_update().get(id=payment_intent.id)

        if intent.status not in {PaymentIntent.Status.CREATED, PaymentIntent.Status.PENDING}:
            raise ValueError("Payment intent cannot be paid in current status.")
        if intent.payment_method != PaymentIntent.PaymentMethod.WALLET:
            raise ValueError("Payment method must be wallet.")

        wallet = intent.wallet or get_or_create_wallet(intent.user)
        wallet = Wallet.objects.select_for_update().get(id=wallet.id)

        if wallet.status != Wallet.Status.ACTIVE:
            raise ValueError("Wallet is not active.")

        available_balance = confirmed_wallet_balance(wallet)
        if available_balance < intent.amount:
            raise ValueError("Insufficient wallet balance.")

        tx_idempotency = f"intent_payment:{intent.id}"
        tx = create_wallet_transaction(
            wallet=wallet,
            transaction_type=WalletTransaction.TransactionType.PAYMENT,
            direction=WalletTransaction.Direction.DEBIT,
            amount=intent.amount,
            currency=intent.currency,
            status=WalletTransaction.Status.CONFIRMED,
            reference_type=intent.service_type,
            reference_id=intent.reference_id,
            description=f"Payment for {intent.service_type}",
            idempotency_key=tx_idempotency,
            metadata={"payment_intent_id": str(intent.id)},
            created_by=intent.user,
        )

        if tx.status != WalletTransaction.Status.CONFIRMED:
            raise ValueError("Wallet transaction is not confirmed.")

        intent.status = PaymentIntent.Status.SUCCEEDED
        intent.paid_at = timezone.now()
        intent.save(update_fields=["status", "paid_at", "updated_at"])
        return intent


def calculate_platform_fee(service_type: str, amount: Decimal) -> Decimal:
    rule = PlatformFeeRule.objects.filter(service_type=service_type, is_active=True).first()
    if not rule:
        return Decimal("0.00")

    if rule.fee_type == PlatformFeeRule.FeeType.PERCENTAGE:
        return (amount * rule.value / Decimal("100")).quantize(Decimal("0.01"))
    return min(rule.value, amount)


def create_provider_earning(
    *,
    payment_intent: PaymentIntent,
    provider_user,
    provider_type: str,
):
    if payment_intent.status != PaymentIntent.Status.SUCCEEDED:
        raise ValueError("Provider earning can be created only after successful payment.")

    fee_amount = calculate_platform_fee(payment_intent.service_type, payment_intent.amount)
    gross = payment_intent.amount
    net = gross - fee_amount

    earning, _ = ProviderEarning.objects.get_or_create(
        service_type=payment_intent.service_type,
        reference_id=payment_intent.reference_id,
        defaults={
            "provider_user": provider_user,
            "provider_type": provider_type,
            "payment_intent": payment_intent,
            "gross_amount": gross,
            "platform_fee_amount": fee_amount,
            "net_amount": net,
            "currency": payment_intent.currency,
            "status": ProviderEarning.Status.PENDING,
            "metadata": {"source": "payment_intent"},
        },
    )
    return earning
