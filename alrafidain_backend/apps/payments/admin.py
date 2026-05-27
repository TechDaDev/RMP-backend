from django.contrib import admin

from .models import PaymentIntent, PlatformFeeRule, ProviderEarning, Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "currency", "cached_balance", "status", "created_at"]
    list_filter = ["status", "currency", "created_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["cached_balance", "created_at", "updated_at"]


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "wallet",
        "transaction_type",
        "direction",
        "amount",
        "currency",
        "status",
        "reference_type",
        "reference_id",
        "created_at",
    ]
    list_filter = ["transaction_type", "direction", "status", "currency", "created_at"]
    search_fields = ["wallet__user__email", "idempotency_key", "reference_type", "description"]
    readonly_fields = ["confirmed_at", "created_at", "updated_at"]


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "service_type",
        "reference_id",
        "amount",
        "currency",
        "status",
        "payment_method",
        "created_at",
    ]
    list_filter = ["service_type", "status", "payment_method", "currency", "created_at"]
    search_fields = ["user__email", "idempotency_key", "provider_transaction_id", "external_reference_id"]
    readonly_fields = ["paid_at", "cancelled_at", "refunded_at", "created_at", "updated_at"]


@admin.register(ProviderEarning)
class ProviderEarningAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "provider_user",
        "provider_type",
        "service_type",
        "reference_id",
        "gross_amount",
        "platform_fee_amount",
        "net_amount",
        "status",
        "created_at",
    ]
    list_filter = ["provider_type", "service_type", "status", "currency", "created_at"]
    search_fields = ["provider_user__email", "reference_id"]
    readonly_fields = ["available_at", "paid_at", "cancelled_at", "created_at", "updated_at"]


@admin.register(PlatformFeeRule)
class PlatformFeeRuleAdmin(admin.ModelAdmin):
    list_display = ["id", "service_type", "fee_type", "value", "currency", "is_active", "created_at"]
    list_filter = ["service_type", "fee_type", "is_active", "currency", "created_at"]
    search_fields = ["service_type"]
