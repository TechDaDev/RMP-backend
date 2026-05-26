from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.policies import RoleAccessPolicy

from .models import PharmacyPrescriptionRequest, PharmacyPrescriptionRequestItem
from .serializers import (
    PharmacyPrescriptionRequestCreateSerializer,
    PharmacyPrescriptionRequestDetailSerializer,
    PharmacyPrescriptionRequestListSerializer,
    PharmacyQuoteSerializer,
)


class PharmacyPrescriptionRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = PharmacyPrescriptionRequest.objects.select_related(
            "prescription",
            "patient",
            "pharmacy",
            "pharmacy__user",
            "requested_by",
        ).prefetch_related("items")

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_pharmacist(user):
            queryset = queryset.filter(pharmacy__user=user)
        elif RoleAccessPolicy.is_patient(user):
            queryset = queryset.filter(patient=user)
        elif RoleAccessPolicy.is_doctor(user):
            queryset = queryset.filter(prescription__doctor=user)
        else:
            queryset = queryset.none()

        status_filter = self.request.query_params.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        pharmacy_filter = self.request.query_params.get("pharmacy", "").strip()
        if pharmacy_filter:
            if RoleAccessPolicy.is_admin_or_staff(user):
                queryset = queryset.filter(pharmacy_id=pharmacy_filter)
            elif RoleAccessPolicy.is_pharmacist(user):
                queryset = queryset.filter(pharmacy_id=pharmacy_filter, pharmacy__user=user)

        prescription_filter = self.request.query_params.get("prescription", "").strip()
        if prescription_filter:
            queryset = queryset.filter(prescription_id=prescription_filter)

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return PharmacyPrescriptionRequestCreateSerializer
        if self.action == "retrieve":
            return PharmacyPrescriptionRequestDetailSerializer
        if self.action == "quote":
            return PharmacyQuoteSerializer
        return PharmacyPrescriptionRequestListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        prescription = validated["prescription"]
        pharmacy = validated["pharmacy"]

        try:
            with transaction.atomic():
                request_obj = PharmacyPrescriptionRequest.objects.create(
                    prescription=prescription,
                    patient=prescription.patient,
                    pharmacy=pharmacy,
                    requested_by=request.user,
                    status=PharmacyPrescriptionRequest.Status.PENDING,
                    patient_notes=validated.get("patient_notes") or "",
                    total_price="0.00",
                )

                request_items = []
                for item in prescription.items.all():
                    request_items.append(
                        PharmacyPrescriptionRequestItem(
                            request=request_obj,
                            prescription_item=item,
                            requested_name_snapshot=item.display_drug_name,
                            availability_status=PharmacyPrescriptionRequestItem.AvailabilityStatus.PENDING,
                            quantity=1,
                            unit_price="0.00",
                            total_price="0.00",
                        )
                    )

                PharmacyPrescriptionRequestItem.objects.bulk_create(request_items)
        except IntegrityError as exc:
            return Response(
                {
                    "success": False,
                    "message": "Duplicate active pending/quoted request for this pharmacy is not allowed.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        output = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request})
        return Response(
            {"success": True, "message": "Pharmacy request created.", "data": output.data},
            status=status.HTTP_201_CREATED,
        )

    def _can_quote(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_pharmacist(user) and request_obj.pharmacy.user_id == user.id

    def _can_accept_or_reject(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_patient(user) and request_obj.patient_id == user.id

    def _can_cancel(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        if RoleAccessPolicy.is_patient(user) and request_obj.patient_id == user.id:
            return True
        if RoleAccessPolicy.is_doctor(user) and request_obj.prescription.doctor_id == user.id:
            return True
        if RoleAccessPolicy.is_pharmacist(user) and request_obj.pharmacy.user_id == user.id:
            return True
        return False

    def _can_complete(self, user, request_obj):
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        return RoleAccessPolicy.is_pharmacist(user) and request_obj.pharmacy.user_id == user.id

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

        serializer = PharmacyQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            for item_payload in serializer.validated_data["items"]:
                prescription_item_id = item_payload["prescription_item"]
                try:
                    request_item = request_obj.items.select_for_update().get(
                        prescription_item_id=prescription_item_id
                    )
                except PharmacyPrescriptionRequestItem.DoesNotExist:
                    return Response(
                        {
                            "success": False,
                            "message": "One or more prescription items are not part of this request.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                inventory_item = item_payload.get("inventory_item")
                availability_status = item_payload["availability_status"]

                if inventory_item:
                    if inventory_item.pharmacy_id != request_obj.pharmacy_id:
                        return Response(
                            {
                                "success": False,
                                "message": "Inventory item must belong to the same pharmacy.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if not inventory_item.is_active:
                        return Response(
                            {"success": False, "message": "Inactive inventory cannot be selected."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if (
                        availability_status
                        != PharmacyPrescriptionRequestItem.AvailabilityStatus.UNAVAILABLE
                        and not inventory_item.is_available
                    ):
                        return Response(
                            {
                                "success": False,
                                "message": "Unavailable inventory cannot be selected for available/substituted quote.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                request_item.inventory_item = inventory_item
                request_item.availability_status = availability_status
                request_item.quoted_name = item_payload.get("quoted_name") or request_item.quoted_name
                request_item.quantity = item_payload.get("quantity", request_item.quantity)
                request_item.unit_price = item_payload.get("unit_price", request_item.unit_price)
                request_item.substitution_note = item_payload.get("substitution_note")
                request_item.pharmacy_note = item_payload.get("pharmacy_note")

                if availability_status == PharmacyPrescriptionRequestItem.AvailabilityStatus.UNAVAILABLE:
                    request_item.unit_price = 0
                    request_item.total_price = 0
                else:
                    request_item.total_price = request_item.unit_price * request_item.quantity

                request_item.save()

            request_obj.pharmacy_notes = serializer.validated_data.get("pharmacy_notes") or ""
            request_obj.status = PharmacyPrescriptionRequest.Status.QUOTED
            request_obj.recalculate_total_price()
            request_obj.save(update_fields=["pharmacy_notes", "status", "total_price", "updated_at"])

        data = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote updated.", "data": data})

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_accept_or_reject(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != PharmacyPrescriptionRequest.Status.QUOTED:
            return Response(
                {"success": False, "message": "Only quoted requests can be accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request_obj.items.filter(
            availability_status__in=[
                PharmacyPrescriptionRequestItem.AvailabilityStatus.AVAILABLE,
                PharmacyPrescriptionRequestItem.AvailabilityStatus.SUBSTITUTED,
            ]
        ).exists():
            return Response(
                {
                    "success": False,
                    "message": "Request must have at least one available/substituted item.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if PharmacyPrescriptionRequest.objects.filter(
            prescription=request_obj.prescription,
            status__in=[
                PharmacyPrescriptionRequest.Status.ACCEPTED,
                PharmacyPrescriptionRequest.Status.COMPLETED,
            ],
        ).exclude(id=request_obj.id).exists():
            return Response(
                {
                    "success": False,
                    "message": "Prescription already has an accepted/completed request.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = PharmacyPrescriptionRequest.Status.ACCEPTED
        request_obj.accepted_at = timezone.now()
        request_obj.save(update_fields=["status", "accepted_at", "updated_at"])

        data = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote accepted.", "data": data})

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_accept_or_reject(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != PharmacyPrescriptionRequest.Status.QUOTED:
            return Response(
                {"success": False, "message": "Only quoted requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rejection_reason = (request.data.get("rejection_reason") or "").strip()

        request_obj.status = PharmacyPrescriptionRequest.Status.REJECTED
        request_obj.rejection_reason = rejection_reason
        request_obj.rejected_at = timezone.now()
        request_obj.save(update_fields=["status", "rejection_reason", "rejected_at", "updated_at"])

        data = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Quote rejected.", "data": data})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_cancel(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status not in {
            PharmacyPrescriptionRequest.Status.PENDING,
            PharmacyPrescriptionRequest.Status.QUOTED,
        }:
            return Response(
                {"success": False, "message": "Only pending/quoted requests can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = PharmacyPrescriptionRequest.Status.CANCELLED
        request_obj.cancelled_at = timezone.now()
        request_obj.save(update_fields=["status", "cancelled_at", "updated_at"])

        data = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Request cancelled.", "data": data})

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        request_obj = self.get_object()

        if not self._can_complete(request.user, request_obj):
            return Response({"success": False, "message": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if request_obj.status != PharmacyPrescriptionRequest.Status.ACCEPTED:
            return Response(
                {"success": False, "message": "Only accepted requests can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_obj.status = PharmacyPrescriptionRequest.Status.COMPLETED
        request_obj.completed_at = timezone.now()
        request_obj.save(update_fields=["status", "completed_at", "updated_at"])

        data = PharmacyPrescriptionRequestDetailSerializer(request_obj, context={"request": request}).data
        return Response({"success": True, "message": "Request completed.", "data": data})
