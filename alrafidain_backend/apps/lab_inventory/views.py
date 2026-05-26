from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.common.policies import RoleAccessPolicy

from .models import LabTestOffering
from .permissions import IsLabInventoryAccess
from .serializers import (
    LabTestOfferingCreateUpdateSerializer,
    LabTestOfferingDetailSerializer,
    LabTestOfferingListSerializer,
)


class LabTestOfferingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsLabInventoryAccess]

    def get_queryset(self):
        queryset = LabTestOffering.objects.select_related("lab", "lab__user", "lab_test").prefetch_related(
            "lab_test__aliases"
        )

        user = self.request.user
        queryset = queryset.filter(is_active=True)

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_laboratorian(user):
            queryset = queryset.filter(lab__user=user)
        else:
            queryset = queryset.filter(is_available=True)

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(lab_test__name__icontains=search)
                | Q(lab_test__short_name__icontains=search)
                | Q(lab_test__loinc_code__icontains=search)
                | Q(lab_test__aliases__alias__icontains=search)
                | Q(custom_test_name__icontains=search)
                | Q(local_name__icontains=search)
                | Q(sample_type_override__icontains=search)
            ).distinct()

        available = self.request.query_params.get("available")
        if available is not None:
            normalized = available.strip().lower()
            if normalized in {"true", "1", "yes"}:
                queryset = queryset.filter(is_available=True)
            elif normalized in {"false", "0", "no"}:
                queryset = queryset.filter(is_available=False)

        lab_test_id = self.request.query_params.get("lab_test", "").strip()
        if lab_test_id:
            queryset = queryset.filter(lab_test_id=lab_test_id)

        lab_id = self.request.query_params.get("lab", "").strip()
        if lab_id:
            if RoleAccessPolicy.is_admin_or_staff(user):
                queryset = queryset.filter(lab_id=lab_id)
            elif RoleAccessPolicy.is_laboratorian(user):
                queryset = queryset.filter(lab_id=lab_id)

        category = self.request.query_params.get("category", "").strip()
        if category:
            queryset = queryset.filter(lab_test__category__icontains=category)

        sample_type = self.request.query_params.get("sample_type", "").strip()
        if sample_type:
            queryset = queryset.filter(
                Q(sample_type_override__icontains=sample_type)
                | Q(lab_test__sample_type__icontains=sample_type)
            )

        return queryset.order_by("-updated_at")

    def get_serializer_class(self):
        if self.action == "list":
            return LabTestOfferingListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return LabTestOfferingCreateUpdateSerializer
        return LabTestOfferingDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if RoleAccessPolicy.is_laboratorian(self.request.user):
            try:
                context["resolved_lab"] = self.request.user.laboratorian_profile
            except Exception:
                context["resolved_lab"] = None
        return context

    def perform_create(self, serializer):
        user = self.request.user

        if RoleAccessPolicy.is_admin_or_staff(user):
            lab = serializer.validated_data.get("lab")
            if not lab:
                raise ValidationError({"lab": "This field is required for admin/staff."})
        elif RoleAccessPolicy.is_laboratorian(user):
            try:
                own_lab = user.laboratorian_profile
            except Exception as exc:
                raise ValidationError({"lab": "Laboratorian profile is required."}) from exc

            supplied_lab = serializer.validated_data.get("lab")
            if supplied_lab and supplied_lab.id != own_lab.id:
                raise ValidationError({"lab": "You can only create offerings for your own lab."})
            lab = own_lab
        else:
            raise PermissionDenied("You do not have permission to create lab offerings.")

        serializer.validated_data.pop("lab", None)

        try:
            with transaction.atomic():
                serializer.save(lab=lab)
        except IntegrityError as exc:
            raise ValidationError(
                {"lab_test": "An active offering already exists for this lab and lab test."}
            ) from exc

    def perform_update(self, serializer):
        user = self.request.user
        if not RoleAccessPolicy.is_admin_or_staff(user):
            serializer.validated_data.pop("lab", None)

        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                {"lab_test": "An active offering already exists for this lab and lab test."}
            ) from exc

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
