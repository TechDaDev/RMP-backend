from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response

from .models import LabTest
from .serializers import (
    LabTestCreateUpdateSerializer,
    LabTestDetailSerializer,
    LabTestListSerializer,
)


class IsAuthenticatedReadAdminWrite(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff or request.user.is_superuser


class LabTestViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedReadAdminWrite]

    def get_queryset(self):
        queryset = LabTest.objects.filter(is_active=True).prefetch_related("aliases")

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(short_name__icontains=search)
                | Q(loinc_code__icontains=search)
                | Q(category__icontains=search)
                | Q(component__icontains=search)
                | Q(system__icontains=search)
                | Q(sample_type__icontains=search)
                | Q(aliases__alias__icontains=search)
            ).distinct()

        category = self.request.query_params.get("category", "").strip()
        if category:
            queryset = queryset.filter(category__icontains=category)

        sample_type = self.request.query_params.get("sample_type", "").strip()
        if sample_type:
            queryset = queryset.filter(sample_type__icontains=sample_type)

        verified = self.request.query_params.get("verified", "").strip().lower()
        if verified == "true":
            queryset = queryset.filter(is_verified=True)
        elif verified == "false":
            queryset = queryset.filter(is_verified=False)

        return queryset.order_by("name")

    def get_serializer_class(self):
        if self.action == "list":
            return LabTestListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return LabTestCreateUpdateSerializer
        return LabTestDetailSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
