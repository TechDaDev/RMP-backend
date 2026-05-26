from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.common.policies import RoleAccessPolicy

from .models import PharmacyDrugInventory
from .permissions import IsPharmacyInventoryAccess
from .serializers import (
    PharmacyDrugInventoryCreateUpdateSerializer,
    PharmacyDrugInventoryDetailSerializer,
    PharmacyDrugInventoryListSerializer,
)


class PharmacyDrugInventoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPharmacyInventoryAccess]

    def get_queryset(self):
        queryset = PharmacyDrugInventory.objects.select_related("pharmacy", "pharmacy__user", "drug")

        user = self.request.user
        queryset = queryset.filter(is_active=True)

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_pharmacist(user):
            queryset = queryset.filter(pharmacy__user=user)
        else:
            queryset = queryset.filter(is_available=True)

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(drug__name__icontains=search)
                | Q(drug__generic_name__icontains=search)
                | Q(drug__brand_name__icontains=search)
                | Q(drug__rxnorm_rxcui__icontains=search)
                | Q(drug__aliases__alias__icontains=search)
                | Q(custom_drug_name__icontains=search)
                | Q(brand_name__icontains=search)
                | Q(strength__icontains=search)
                | Q(form__icontains=search)
            ).distinct()

        available = self.request.query_params.get("available")
        if available is not None:
            normalized = available.strip().lower()
            if normalized in {"true", "1", "yes"}:
                queryset = queryset.filter(is_available=True)
            elif normalized in {"false", "0", "no"}:
                queryset = queryset.filter(is_available=False)

        stock_status = self.request.query_params.get("stock_status", "").strip()
        if stock_status:
            queryset = queryset.filter(stock_status=stock_status)

        drug_id = self.request.query_params.get("drug", "").strip()
        if drug_id:
            queryset = queryset.filter(drug_id=drug_id)

        pharmacy_id = self.request.query_params.get("pharmacy", "").strip()
        if pharmacy_id:
            if RoleAccessPolicy.is_admin_or_staff(user):
                queryset = queryset.filter(pharmacy_id=pharmacy_id)
            elif RoleAccessPolicy.is_pharmacist(user):
                queryset = queryset.filter(pharmacy_id=pharmacy_id)

        return queryset.order_by("-updated_at")

    def get_serializer_class(self):
        if self.action == "list":
            return PharmacyDrugInventoryListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return PharmacyDrugInventoryCreateUpdateSerializer
        return PharmacyDrugInventoryDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if RoleAccessPolicy.is_pharmacist(self.request.user):
            try:
                context["resolved_pharmacy"] = self.request.user.pharmacist_profile
            except Exception:
                context["resolved_pharmacy"] = None
        return context

    def perform_create(self, serializer):
        user = self.request.user

        if RoleAccessPolicy.is_admin_or_staff(user):
            pharmacy = serializer.validated_data.get("pharmacy")
            if not pharmacy:
                raise ValidationError({"pharmacy": "This field is required for admin/staff."})
        elif RoleAccessPolicy.is_pharmacist(user):
            try:
                pharmacy = user.pharmacist_profile
            except Exception as exc:
                raise ValidationError({"pharmacy": "Pharmacist profile is required."}) from exc
        else:
            raise PermissionDenied("You do not have permission to create inventory records.")

        serializer.validated_data.pop("pharmacy", None)

        try:
            with transaction.atomic():
                serializer.save(pharmacy=pharmacy)
        except IntegrityError as exc:
            raise ValidationError(
                {"drug": "An active inventory entry already exists for this pharmacy and drug."}
            ) from exc

    def perform_update(self, serializer):
        user = self.request.user
        if not RoleAccessPolicy.is_admin_or_staff(user):
            serializer.validated_data.pop("pharmacy", None)

        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                {"drug": "An active inventory entry already exists for this pharmacy and drug."}
            ) from exc

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
