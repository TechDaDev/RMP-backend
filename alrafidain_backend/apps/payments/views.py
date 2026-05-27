from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.policies import RoleAccessPolicy

from .models import PaymentIntent, WalletTransaction
from .permissions import IsAdminOrStaff
from .serializers import (
    ManualRechargeSerializer,
    PaymentIntentCreateSerializer,
    PaymentIntentSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
)
from .services import (
    create_manual_recharge,
    create_payment_intent,
    get_or_create_wallet,
    pay_with_wallet,
)

User = get_user_model()


class WalletMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_or_create_wallet(request.user)
        return Response(WalletSerializer(wallet).data)


class WalletTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WalletTransaction.objects.select_related("wallet", "wallet__user", "created_by")
        user = self.request.user

        if RoleAccessPolicy.is_admin_or_staff(user):
            wallet_id = self.request.query_params.get("wallet")
            user_id = self.request.query_params.get("user")
            if wallet_id:
                qs = qs.filter(wallet_id=wallet_id)
            if user_id:
                qs = qs.filter(wallet__user_id=user_id)
            return qs.order_by("-created_at")

        wallet = get_or_create_wallet(user)
        return qs.filter(wallet=wallet).order_by("-created_at")


class ManualRechargeAdminView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        serializer = ManualRechargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        target_user = get_object_or_404(User, id=payload["user"])
        wallet = get_or_create_wallet(target_user)

        idempotency_key = payload.get("idempotency_key")
        if idempotency_key:
            existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return Response(
                    {
                        "wallet": WalletSerializer(wallet).data,
                        "transaction": WalletTransactionSerializer(existing).data,
                    },
                    status=status.HTTP_200_OK,
                )

        tx = create_manual_recharge(
            wallet=wallet,
            amount=payload["amount"],
            created_by=request.user,
            description=payload.get("description", ""),
            idempotency_key=idempotency_key,
        )

        wallet.refresh_from_db(fields=["cached_balance", "updated_at"])
        return Response(
            {
                "wallet": WalletSerializer(wallet).data,
                "transaction": WalletTransactionSerializer(tx).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentIntentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PaymentIntent.objects.select_related("user", "wallet")
        user = self.request.user
        if RoleAccessPolicy.is_admin_or_staff(user):
            return qs.order_by("-created_at")
        return qs.filter(user=user).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentIntentCreateSerializer
        return PaymentIntentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        # TODO: validate service ownership and authoritative amount from domain objects.
        intent = create_payment_intent(
            user=request.user,
            service_type=payload["service_type"],
            reference_id=payload.get("reference_id"),
            amount=payload["amount"],
            payment_method=payload["payment_method"],
            idempotency_key=payload.get("idempotency_key"),
            metadata=payload.get("metadata") or {},
        )
        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="pay-wallet")
    def pay_wallet(self, request, pk=None):
        intent = self.get_object()

        if not RoleAccessPolicy.is_admin_or_staff(request.user) and intent.user_id != request.user.id:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        try:
            paid_intent = pay_with_wallet(intent)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: optionally create provider earnings here once provider-resolution mapping is finalized.
        return Response(PaymentIntentSerializer(paid_intent).data, status=status.HTTP_200_OK)
