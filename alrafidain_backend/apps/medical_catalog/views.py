from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import Drug
from .permissions import IsAuthenticatedReadAdminWrite
from .serializers import (
    DrugCreateUpdateSerializer,
    DrugDetailSerializer,
    DrugListSerializer,
)


class DrugViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedReadAdminWrite]

    def get_queryset(self):
        queryset = Drug.objects.filter(is_active=True).prefetch_related("aliases")

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(generic_name__icontains=search)
                | Q(brand_name__icontains=search)
                | Q(rxnorm_rxcui__icontains=search)
                | Q(aliases__alias__icontains=search)
            ).distinct()

        return queryset.order_by("name")

    def get_serializer_class(self):
        if self.action == "list":
            return DrugListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return DrugCreateUpdateSerializer
        return DrugDetailSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
