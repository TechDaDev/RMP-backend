from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from rest_framework import serializers

from apps.common.file_validation import validate_uploaded_file

from .models import (
    PaymentIntent,
    PlatformFeeRule,
    ProviderEarning,
    Wallet,
    WalletRechargeRequest,
    WalletTransaction,
)


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ["id", "user", "currency", "cached_balance", "status", "created_at", "updated_at"]
        read_only_fields = fields


class AdminWalletSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_type = serializers.CharField(source="user.user_type", read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id",
            "user",
            "user_email",
            "user_full_name",
            "user_type",
            "currency",
            "cached_balance",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "wallet",
            "transaction_type",
            "direction",
            "amount",
            "currency",
            "status",
            "reference_type",
            "reference_id",
            "description",
            "idempotency_key",
            "metadata",
            "created_by",
            "confirmed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlatformFeeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformFeeRule
        fields = [
            "id",
            "service_type",
            "fee_type",
            "value",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ProviderEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderEarning
        fields = [
            "id",
            "provider_user",
            "provider_type",
            "service_type",
            "reference_id",
            "payment_intent",
            "gross_amount",
            "platform_fee_amount",
            "net_amount",
            "currency",
            "status",
            "metadata",
            "created_at",
            "updated_at",
            "available_at",
            "paid_at",
            "cancelled_at",
        ]
        read_only_fields = fields


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id",
            "user",
            "wallet",
            "service_type",
            "reference_id",
            "amount",
            "currency",
            "status",
            "payment_method",
            "provider",
            "provider_transaction_id",
            "external_reference_id",
            "idempotency_key",
            "metadata",
            "created_at",
            "updated_at",
            "paid_at",
            "cancelled_at",
            "refunded_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "wallet",
            "status",
            "provider",
            "provider_transaction_id",
            "external_reference_id",
            "created_at",
            "updated_at",
            "paid_at",
            "cancelled_at",
            "refunded_at",
        ]


class PaymentIntentCreateSerializer(serializers.Serializer):
    service_type = serializers.ChoiceField(choices=PaymentIntent.ServiceType.choices)
    reference_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=PaymentIntent.PaymentMethod.choices)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate_payment_method(self, value):
        if value not in {
            PaymentIntent.PaymentMethod.WALLET,
            PaymentIntent.PaymentMethod.MANUAL,
        }:
            raise serializers.ValidationError("Only wallet/manual payment methods are allowed.")
        return value

    def validate(self, attrs):
        service_type = attrs["service_type"]
        reference_id = attrs.get("reference_id")
        amount = attrs.get("amount")

        if service_type == PaymentIntent.ServiceType.WALLET_RECHARGE:
            if amount is None:
                raise serializers.ValidationError({"amount": "This field is required for wallet recharge."})
            if reference_id is not None:
                raise serializers.ValidationError(
                    {"reference_id": "Wallet recharge does not require a reference_id."}
                )
        else:
            if reference_id is None:
                raise serializers.ValidationError(
                    {"reference_id": "This field is required for service payments."}
                )
            if amount is not None:
                raise serializers.ValidationError(
                    {"amount": "Amount is derived from the service object and must not be provided."}
                )

        if reference_id and PaymentIntent.objects.filter(
            service_type=service_type,
            reference_id=reference_id,
            status=PaymentIntent.Status.SUCCEEDED,
        ).exists():
            raise serializers.ValidationError("This service object already has a succeeded payment.")

        attrs["idempotency_key"] = attrs.get("idempotency_key") or f"intent:{uuid4().hex}"
        return attrs


class ManualRechargeSerializer(serializers.Serializer):
    user = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_amount(self, value: Decimal):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class WalletRechargeRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True)
    receipt_file = serializers.FileField(required=True)

    def validate_amount(self, value: Decimal):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate_receipt_file(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=settings.TRANSFER_RECEIPT_ALLOWED_EXTENSIONS,
            allowed_content_types=settings.TRANSFER_RECEIPT_ALLOWED_CONTENT_TYPES,
            max_size_mb=settings.MAX_TRANSFER_RECEIPT_UPLOAD_MB,
        )
        return value


class WalletRechargeRequestReviewSerializer(serializers.Serializer):
    review_note = serializers.CharField(required=False, allow_blank=True)


class WalletRechargeRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    reviewer_email = serializers.EmailField(source="reviewed_by.email", read_only=True)
    approved_transaction_id = serializers.UUIDField(source="approved_transaction.id", read_only=True)
    receipt_file_url = serializers.SerializerMethodField()

    def get_receipt_file_url(self, obj):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not obj.receipt_file:
            return None

        is_reviewer = False
        if actor and actor.is_authenticated:
            try:
                from .permissions import is_finance_reviewer

                is_reviewer = is_finance_reviewer(actor)
            except Exception:
                is_reviewer = False

        is_owner_with_pending_access = (
            actor
            and actor.is_authenticated
            and actor.id == obj.user_id
            and obj.status == WalletRechargeRequest.Status.PENDING_REVIEW
        )

        if not (is_reviewer or is_owner_with_pending_access):
            return None

        # Some private/custom storage backends do not expose a direct URL.
        # Avoid raising and return null so create/list endpoints stay stable.
        try:
            file_url = obj.receipt_file.url
        except Exception:
            return None
        if request is not None:
            return request.build_absolute_uri(file_url)
        return file_url

    class Meta:
        model = WalletRechargeRequest
        fields = [
            "id",
            "user",
            "user_email",
            "wallet",
            "amount",
            "currency",
            "note",
            "status",
            "receipt_file_url",
            "original_filename",
            "file_size",
            "mime_type",
            "reviewed_by",
            "reviewer_email",
            "reviewed_at",
            "review_note",
            "approved_transaction_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
