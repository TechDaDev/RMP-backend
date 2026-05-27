from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.policies import RoleAccessPolicy

from .models import LabOrderRequest, LabOrderRequestItem
from .serializers import (
    LabOrderRequestCreateSerializer,
    LabOrderRequestDetailSerializer,
    LabOrderRequestListSerializer,
    LabQuoteSerializer,
    LabRequestActionSerializer,
)


class LabOrderRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = LabOrderRequest.objects.select_related(
            "lab_order",
            "patient",
            "lab",
            "lab__user",
            "requested_by",
        ).prefetch_related("items")

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_laboratorian(user):
            queryset = queryset.filter(lab__user=user)
        elif RoleAccessPolicy.is_patient(user):
            queryset = queryset.filter(patient=user)
        elif RoleAccessPolicy.is_doctor(user):
            queryset = queryset.filter(lab_order__doctor=user)
        else:
            queryset = queryset.none()

        status_filter = self.request.query_params.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        lab_filter = self.request.query_params.get("lab", "").strip()
        if lab_filter:
            if RoleAccessPolicy.is_admin_or_staff(user):
                queryset = queryset.filter(lab_id=lab_filter)
            elif RoleAccessPolicy.is_laboratorian(user):
                queryset = queryset.filter(lab_id=lab_filter, lab__user=user)

        lab_order_filter = self.request.query_params.get("lab_order", "").strip()
        if lab_order_filter:
            queryset = queryset.filter(lab_order_id=lab_order_filter)

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return LabOrderRequestCreateSerializer
        if self.action == "retrieve":
            return LabOrderRequestDetailSerializer
        if self.action == "quote":
            return LabQuoteSerializer
        if self.action in {"reject", "cancel"}:
            return LabRequestActionSerializer
        return LabOrderRequestListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        lab_order = validated["lab_order"]
        lab = validated["lab"]

        try:
            with transaction.atomic():
                request_obj = LabOrderRequest.objects.create(
                    lab_order=lab_order,
                    patient=lab_order.patient,
                    lab=lab,
                    requested_by=request.user,
                    status=LabOrderRequest.Status.PENDING,
                    patient_notes=validated.get("patient_notes") or "",
                    total_price="0.00",
                )

                request_items = []
                for item in lab_order.items.all():
                    request_items.append(
                        LabOrderRequestItem(
                            request=request_obj,
                            lab_order_item=item,
                            requested_name_snapshot=item.display_test_name,
                            availability_status=LabOrderRequestItem.AvailabilityStatus.PENDING,
                            quantity=1,
                            unit_price="0.00",
                            total_price="0.00",
                        )
                    )

                LabOrderRequestItem.objects.bulk_create(request_items)
        except IntegrityError:
            return Response(
                {
                    "success": False,
                    "message": "Duplicate active pending/quoted request for this lab is not allowed.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        output = LabOrderRequestDetailSerializer(request_obj, context={"request": request})
        return Response(
            {"success": True, "message": "Lab request created.", "data": output.data},
            status=status.HTTP_201_CREATED,
        )

    def _can_quote(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_laboratorian(user) and request_obj.lab.user_id == user.id

    def _can_accept_or_reject(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_patient(user) and request_obj.patient_id == user.id

    def _can_cancel(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        if RoleAccessPolicy.is_patient(user) and request_obj.patient_id == user.id:
            return True
        if RoleAccessPolicy.is_doctor(user) and request_obj.lab_order.doctor_id == user.id:
            return True
        if RoleAccessPolicy.is_laboratorian(user) and request_obj.lab.user_id == user.id:
            return True
        return False

    def _can_complete(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_laboratorian(user) and request_obj.lab.user_id == user.id

    @action(detail=True, methods=["post"], url_path="quote")
    def quote(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_quote(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if not request_obj.can_be_quoted:
            return Response(
                {"success": False, "message": "Request cannot be quoted in current status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = LabQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            for item_payload in serializer.validated_data["items"]:
                lab_order_item_id = item_payload["lab_order_item"]
                try:
                    request_item = request_obj.items.select_for_update().get(
                        lab_order_item_id=lab_order_item_id
                    )
                except LabOrderRequestItem.DoesNotExist:
                    return Response(
                        {
                            "success": False,
                            "message": "One or more lab order items are not part of this request.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                offering = item_payload.get("offering")
                availability_status = item_payload["availability_status"]

                if offering:
                    if offering.lab_id != request_obj.lab_id:
                        return Response(
                            {
                                "success": False,
                                "message": "Offering must belong to the same lab.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if not offering.is_active:
                        return Response(
                            {"success": False, "message": "Inactive offering cannot be selected."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if (
                        availability_status != LabOrderRequestItem.AvailabilityStatus.UNAVAILABLE
                        and not offering.is_available
                    ):
                        return Response(
                            {
                                "success": False,
                                "message": "Unavailable offering cannot be selected for available/substituted quote.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                request_item.offering = offering
                request_item.availability_status = availability_status
                request_item.quoted_name = item_payload.get("quoted_name") or request_item.quoted_name
                request_item.quantity = item_payload.get("quantity", request_item.quantity)
                request_item.unit_price = item_payload.get("unit_price", request_item.unit_price)
                request_item.substitution_note = item_payload.get("substitution_note")
                request_item.lab_note = item_payload.get("lab_note")

                if availability_status == LabOrderRequestItem.AvailabilityStatus.UNAVAILABLE:
                    request_item.unit_price = 0
                    request_item.total_price = 0
                else:
                    request_item.total_price = request_item.unit_price * request_item.quantity

                request_item.save()

            request_obj.lab_notes = serializer.validated_data.get("lab_notes") or ""
            request_obj.status = LabOrderRequest.Status.QUOTED
            request_obj.recalculate_total_price()
            request_obj.save(update_fields=["lab_notes", "status", "total_price", "updated_at"])

        data = LabOrderRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote updated.", "data": data})

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_accept_or_reject(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != LabOrderRequest.Status.QUOTED:
            return Response(
                {"success": False, "message": "Only quoted requests can be accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request_obj.items.filter(
            availability_status__in=[
                LabOrderRequestItem.AvailabilityStatus.AVAILABLE,
                LabOrderRequestItem.AvailabilityStatus.SUBSTITUTED,
            ]
        ).exists():
            return Response(
                {
                    "success": False,
                    "message": "Request must have at least one available/substituted item.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if LabOrderRequest.objects.filter(
            lab_order=request_obj.lab_order,
            status__in=[
                LabOrderRequest.Status.ACCEPTED,
                LabOrderRequest.Status.COMPLETED,
            ],
        ).exclude(id=request_obj.id).exists():
            return Response(
                {
                    "success": False,
                    "message": "Lab order already has an accepted/completed request.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = LabOrderRequest.Status.ACCEPTED
        request_obj.accepted_at = timezone.now()
        request_obj.save(update_fields=["status", "accepted_at", "updated_at"])

        data = LabOrderRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote accepted.", "data": data})

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_accept_or_reject(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != LabOrderRequest.Status.QUOTED:
            return Response(
                {"success": False, "message": "Only quoted requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = LabRequestActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rejection_reason = (serializer.validated_data.get("rejection_reason") or "").strip()

        request_obj.status = LabOrderRequest.Status.REJECTED
        request_obj.rejection_reason = rejection_reason
        request_obj.rejected_at = timezone.now()
        request_obj.save(update_fields=["status", "rejection_reason", "rejected_at", "updated_at"])

        data = LabOrderRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote rejected.", "data": data})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_cancel(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status not in {LabOrderRequest.Status.PENDING, LabOrderRequest.Status.QUOTED}:
            return Response(
                {"success": False, "message": "Only pending/quoted requests can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = LabOrderRequest.Status.CANCELLED
        request_obj.cancelled_at = timezone.now()
        request_obj.save(update_fields=["status", "cancelled_at", "updated_at"])

        data = LabOrderRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Request cancelled.", "data": data})

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_complete(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != LabOrderRequest.Status.ACCEPTED:
            return Response(
                {"success": False, "message": "Only accepted requests can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = LabOrderRequest.Status.COMPLETED
        request_obj.completed_at = timezone.now()
        request_obj.save(update_fields=["status", "completed_at", "updated_at"])

        data = LabOrderRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Request completed.", "data": data})
