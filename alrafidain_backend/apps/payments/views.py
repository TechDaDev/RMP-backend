from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.policies import RoleAccessPolicy

from .models import PaymentIntent, Wallet, WalletRechargeRequest, WalletTransaction
from .permissions import IsFinanceReviewer, IsFinancialOrAdmin, is_finance_reviewer, is_financial_or_admin
from .serializers import (
    AdminWalletSerializer,
    ManualRechargeSerializer,
    PaymentIntentCreateSerializer,
    PaymentIntentSerializer,
    WalletRechargeRequestCreateSerializer,
    WalletRechargeRequestReviewSerializer,
    WalletRechargeRequestSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
)
from .services import (
    approve_wallet_recharge_request,
    create_manual_recharge,
    create_payment_intent,
    create_wallet_recharge_request,
    get_or_create_wallet,
    pay_with_wallet,
    reject_wallet_recharge_request,
)

User = get_user_model()


class WalletMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_or_create_wallet(request.user)
        return Response(WalletSerializer(wallet).data)


class AdminWalletViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminWalletSerializer
    permission_classes = [IsAuthenticated, IsFinancialOrAdmin]

    def get_queryset(self):
        qs = Wallet.objects.select_related("user").all().order_by("-created_at")
        params = self.request.query_params

        wallet_id = params.get("wallet_id") or params.get("id")
        user_id = params.get("user") or params.get("user_id")
        email = params.get("email")
        search = params.get("search")
        status_value = params.get("status")

        if wallet_id:
            qs = qs.filter(id=wallet_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if email:
            qs = qs.filter(user__email__icontains=email.strip())
        if status_value:
            qs = qs.filter(status=status_value)
        if search:
            term = search.strip()
            qs = qs.filter(
                Q(user__email__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
            )

        return qs.distinct().order_by("-created_at")


class WalletTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WalletTransaction.objects.select_related("wallet", "wallet__user", "created_by")
        user = self.request.user

        if is_financial_or_admin(user):
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
    permission_classes = [IsAuthenticated, IsFinancialOrAdmin]

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
        if is_financial_or_admin(user):
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

        try:
            intent = create_payment_intent(
                user=request.user,
                service_type=payload["service_type"],
                reference_id=payload.get("reference_id"),
                amount=payload.get("amount"),
                payment_method=payload["payment_method"],
                idempotency_key=payload.get("idempotency_key"),
                metadata=payload.get("metadata") or {},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="pay-wallet")
    def pay_wallet(self, request, pk=None):
        intent = self.get_object()

        if not is_financial_or_admin(request.user) and intent.user_id != request.user.id:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        try:
            paid_intent = pay_with_wallet(intent)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentIntentSerializer(paid_intent).data, status=status.HTTP_200_OK)


class WalletRechargeRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WalletRechargeRequest.objects.select_related(
            "user", "wallet", "reviewed_by", "approved_transaction"
        )
        user = self.request.user
        if is_finance_reviewer(user):
            params = self.request.query_params
            status_value = params.get("status")
            user_id = params.get("user") or params.get("user_id")
            email = params.get("email")

            if status_value:
                qs = qs.filter(status=status_value)
            if user_id:
                qs = qs.filter(user_id=user_id)
            if email:
                qs = qs.filter(user__email__icontains=email.strip())
            return qs.order_by("-created_at")

        return qs.filter(user=user).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return WalletRechargeRequestCreateSerializer
        if self.action in {"approve", "reject"}:
            return WalletRechargeRequestReviewSerializer
        return WalletRechargeRequestSerializer

    def get_permissions(self):
        if self.action in {"approve", "reject"}:
            return [IsAuthenticated(), IsFinanceReviewer()]
        return [permission() for permission in self.permission_classes]

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if is_finance_reviewer(user):
            return obj
        if obj.user_id != user.id:
            self.permission_denied(self.request, message="Forbidden.")
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        try:
            created = create_wallet_recharge_request(
                user=request.user,
                amount=payload["amount"],
                note=payload.get("note", ""),
                receipt_file=payload["receipt_file"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = WalletRechargeRequestSerializer(created, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        obj = super().get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reviewed = approve_wallet_recharge_request(
                request_obj=obj,
                reviewer=request.user,
                review_note=serializer.validated_data.get("review_note", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = WalletRechargeRequestSerializer(reviewed, context={"request": request})
        return Response(output.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        obj = super().get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reviewed = reject_wallet_recharge_request(
                request_obj=obj,
                reviewer=request.user,
                review_note=serializer.validated_data.get("review_note", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = WalletRechargeRequestSerializer(reviewed, context={"request": request})
        return Response(output.data, status=status.HTTP_200_OK)
