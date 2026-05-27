from decimal import Decimal

from rest_framework import serializers

from apps.common.choices import VerificationStatus
from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy
from apps.lab_inventory.models import LabTestOffering
from apps.lab_orders.models import LabOrder
from apps.profiles.models import LaboratorianProfile

from .models import LabOrderRequest, LabOrderRequestItem


class LabOrderRequestItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabOrderRequestItem
        fields = [
            "id",
            "lab_order_item",
            "offering",
            "requested_name_snapshot",
            "quoted_name",
            "quantity",
            "unit_price",
            "total_price",
            "availability_status",
            "substitution_note",
            "lab_note",
            "created_at",
            "updated_at",
        ]


class LabOrderRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabOrderRequest
        fields = [
            "id",
            "lab_order",
            "patient",
            "lab",
            "status",
            "payment_status",
            "payment_intent",
            "paid_at",
            "total_price",
            "currency",
            "created_at",
            "updated_at",
        ]


class LabOrderRequestDetailSerializer(LabOrderRequestListSerializer):
    items = LabOrderRequestItemSerializer(many=True, read_only=True)

    class Meta(LabOrderRequestListSerializer.Meta):
        fields = LabOrderRequestListSerializer.Meta.fields + [
            "requested_by",
            "lab_notes",
            "patient_notes",
            "rejection_reason",
            "payment_failed_at",
            "refunded_at",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",
            "items",
        ]


class LabOrderRequestCreateSerializer(serializers.Serializer):
    lab_order = serializers.PrimaryKeyRelatedField(queryset=LabOrder.objects.all())
    lab = serializers.PrimaryKeyRelatedField(queryset=LaboratorianProfile.objects.all())
    patient_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        user = self.context["request"].user
        lab_order = attrs["lab_order"]
        lab = attrs["lab"]

        if not lab.user.is_active:
            raise serializers.ValidationError({"lab": "Lab user is inactive."})

        if lab.verification_status != VerificationStatus.APPROVED:
            raise serializers.ValidationError({"lab": "Laboratorian profile must be approved."})

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_patient(user):
            if lab_order.patient_id != user.id:
                raise serializers.ValidationError("You can request only your own lab orders.")
        elif RoleAccessPolicy.is_doctor(user):
            if not ClinicalAccessPolicy.can_user_access_lab_order(user, lab_order):
                raise serializers.ValidationError("You cannot request this lab order.")
        else:
            raise serializers.ValidationError("You are not allowed to create lab requests.")

        if LabOrderRequest.objects.filter(
            lab_order=lab_order,
            status__in=[
                LabOrderRequest.Status.ACCEPTED,
                LabOrderRequest.Status.COMPLETED,
            ],
        ).exists():
            raise serializers.ValidationError(
                "Lab order already has an accepted/completed lab request."
            )

        if LabOrderRequest.objects.filter(
            lab_order=lab_order,
            lab=lab,
            status__in=[
                LabOrderRequest.Status.PENDING,
                LabOrderRequest.Status.QUOTED,
            ],
        ).exists():
            raise serializers.ValidationError(
                "Duplicate active pending/quoted request for this lab is not allowed."
            )

        return attrs


class LabQuoteItemInputSerializer(serializers.Serializer):
    lab_order_item = serializers.UUIDField()
    offering = serializers.PrimaryKeyRelatedField(
        queryset=LabTestOffering.objects.all(), required=False, allow_null=True
    )
    availability_status = serializers.ChoiceField(choices=LabOrderRequestItem.AvailabilityStatus.choices)
    quoted_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(required=False, min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)
    substitution_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lab_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        availability_status = attrs["availability_status"]

        if availability_status == LabOrderRequestItem.AvailabilityStatus.UNAVAILABLE:
            attrs["unit_price"] = Decimal("0.00")
            attrs["total_price"] = Decimal("0.00")
            attrs["quantity"] = attrs.get("quantity") or 1
            return attrs

        quantity = attrs.get("quantity")
        unit_price = attrs.get("unit_price")
        if quantity is None or quantity < 1:
            raise serializers.ValidationError({"quantity": "Quantity must be >= 1."})
        if unit_price is None or unit_price < 0:
            raise serializers.ValidationError({"unit_price": "Unit price cannot be negative."})

        attrs["total_price"] = unit_price * quantity
        return attrs


class LabQuoteSerializer(serializers.Serializer):
    lab_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = LabQuoteItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one quote item is required.")

        ids = [str(item["lab_order_item"]) for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate lab_order_item entries are not allowed.")

        return value


class LabRequestActionSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
