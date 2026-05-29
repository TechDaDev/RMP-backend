from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminWalletViewSet,
    ManualRechargeAdminView,
    PaymentIntentViewSet,
    WalletRechargeRequestViewSet,
    WalletMeView,
    WalletTransactionViewSet,
)

router = DefaultRouter()
router.register(r"admin/wallets", AdminWalletViewSet, basename="admin-wallets")
router.register(r"wallet/transactions", WalletTransactionViewSet, basename="wallet-transactions")
router.register(r"intents", PaymentIntentViewSet, basename="payment-intents")
router.register(r"wallet/recharge-requests", WalletRechargeRequestViewSet, basename="wallet-recharge-requests")

urlpatterns = [
    path("wallet/", WalletMeView.as_view(), name="payments-wallet-me"),
    path("admin/manual-recharge/", ManualRechargeAdminView.as_view(), name="payments-manual-recharge"),
]

urlpatterns += router.urls
